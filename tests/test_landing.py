"""Offline landing checks. Requires PyYAML, a shell and a supplied mihomo binary.

python tests/test_landing.py --mihomo /path/to/mihomo --shell /path/to/bash
All proxy credentials and network endpoints below are local test fixtures.
"""

import argparse
import copy
import http.server
import ipaddress
import json
import os
import select
import shutil
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "box_bll/clash/config.yaml"
HELPER = REPO / "box_bll/scripts/box.landing"
EXAMPLE = REPO / "box_bll/clash/landing.example.yaml"
LEGACY = REPO / "tests/fixtures/legacy-config.yaml"
MIHOMO = SHELL = BUSYBOX = None


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def read_exact(sock, size):
    result = b""
    while len(result) < size:
        chunk = sock.recv(size - len(result))
        if not chunk:
            raise EOFError("socket closed")
        result += chunk
    return result


def read_address(sock, kind):
    if kind == 1:
        return socket.inet_ntoa(read_exact(sock, 4))
    if kind == 4:
        return socket.inet_ntop(socket.AF_INET6, read_exact(sock, 16))
    if kind == 3:
        return read_exact(sock, read_exact(sock, 1)[0]).decode()
    raise ValueError(kind)


def address(host, port):
    try:
        ip = ipaddress.ip_address(host)
        encoded = bytes([1 if ip.version == 4 else 4]) + ip.packed
    except ValueError:
        encoded = bytes([3, len(host)]) + host.encode()
    return encoded + struct.pack("!H", port)


def connect_socks(port, host, target_port, command=1):
    sock = socket.create_connection(("127.0.0.1", port), timeout=3)
    sock.sendall(b"\x05\x01\x00")
    assert read_exact(sock, 2) == b"\x05\x00"
    sock.sendall(bytes([5, command, 0]) + address(host, target_port))
    header = read_exact(sock, 4)
    bound_host = read_address(sock, header[3])
    bound_port = struct.unpack("!H", read_exact(sock, 2))[0]
    if header[1] != 0:
        sock.close()
        raise ConnectionError(header[1])
    return sock, bound_host, bound_port


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class SocksHandler(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        sock.settimeout(4)
        try:
            version, count = read_exact(sock, 2)
            assert version == 5
            methods = read_exact(sock, count)
            if self.server.auth:
                if 2 not in methods:
                    sock.sendall(b"\x05\xff")
                    return
                sock.sendall(b"\x05\x02")
                assert read_exact(sock, 1) == b"\x01"
                user = read_exact(sock, read_exact(sock, 1)[0])
                password = read_exact(sock, read_exact(sock, 1)[0])
                good = (user, password) == (b"fixture-user", b"fixture-password")
                self.server.auth_attempts.append(good)
                sock.sendall(b"\x01\x00" if good else b"\x01\x01")
                if not good:
                    return
            else:
                sock.sendall(b"\x05\x00")
            version, command, _, kind = read_exact(sock, 4)
            host = read_address(sock, kind)
            port = struct.unpack("!H", read_exact(sock, 2))[0]
            self.server.requests.append((command, host, port))
            if command != 1 or self.server.reject:
                sock.sendall(b"\x05\x07\x00\x01" + b"\x00" * 6)
                return
            # This fixture must never reach the public Internet.
            if host in ("landing.test", "ordinary.test"):
                host = "127.0.0.1"
            host = getattr(self.server, "hosts", {}).get(host, host)
            assert ipaddress.ip_address(host).is_loopback, host
            with socket.create_connection((host, port), timeout=3) as other:
                sock.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
                while True:
                    ready, _, _ = select.select([sock, other], [], [], 3)
                    if not ready:
                        return
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        (other if source is sock else sock).sendall(data)
        except (OSError, EOFError):
            pass


class WebHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append(self.path)
        data = b"fixture-ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class UdpHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        self.server.requests.append(data)
        sock.sendto(data, self.client_address)


class DnsHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        size = struct.unpack("!H", read_exact(self.request, 2))[0]
        query = read_exact(self.request, size)
        self.server.requests.append(query)
        response = (
            query[:2]
            + b"\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00"
            + query[12:]
            + b"\xc0\x0c\x00\x01\x00\x01"
            + struct.pack("!IH", 60, 4)
            + socket.inet_aton("203.0.113.1")
        )
        self.request.sendall(struct.pack("!H", len(response)) + response)


def server(kind, handler, host="127.0.0.1", **kwargs):
    instance = kind((host, 0), handler)
    instance.requests = []
    instance.auth_attempts = []
    instance.auth = False
    instance.reject = False
    for key, value in kwargs.items():
        setattr(instance, key, value)
    threading.Thread(target=instance.serve_forever, daemon=True).start()
    return instance


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="surfing-landing-")
        self.root = Path(self.temp.name)
        self.config = self.root / "clash/config.yaml"
        write(self.config, CONFIG.read_text(encoding="utf-8"))
        shutil.copyfile(EXAMPLE, self.root / "clash/landing.example.yaml")
        self.addCleanup(self.temp.cleanup)

    def init(self):
        return subprocess.run(
            [
                SHELL,
                HELPER.as_posix(),
                "init",
                self.root.as_posix(),
                self.config.as_posix(),
            ],
            capture_output=True,
            check=True,
        )

    def test_first_install_and_repeated_upgrade(self):
        self.init()
        account = self.root / "clash/private/landing.yaml"
        self.assertEqual(account.read_bytes(), EXAMPLE.read_bytes())
        personal = b"proxies:\n  - {name: 'personal', type: reject}\n"
        account.write_bytes(personal)
        config_before = self.config.read_bytes()
        self.init()
        self.assertEqual(account.read_bytes(), personal)
        self.assertEqual(self.config.read_bytes(), config_before)

    def test_old_subscription_restore_and_idempotence(self):
        text = LEGACY.read_text(encoding="utf-8")
        text = text.replace(
            "此处引入您的Clash订阅链接地址", "https://subscription.invalid/personal"
        )
        write(self.config, text)
        installer = (REPO / "customize.sh").read_text(encoding="utf-8")
        functions = installer.split("extract_subscribe_urls() {", 1)[1].split(
            "install_surfingtile_apk()", 1
        )[0]
        harness = self.root / "restore.sh"
        write(
            harness,
            "set -e\nprint_lang() { :; }\n"
            "CONFIG_FILE=$1\nBACKUP_FILE=$2\n"
            "extract_subscribe_urls() {"
            + functions
            + '\nextract_subscribe_urls\ncp "$3" "$CONFIG_FILE"\nrestore_subscribe_urls\n',
        )
        subprocess.run(
            [
                SHELL,
                harness.as_posix(),
                self.config.as_posix(),
                (self.root / "subscribe_urls_backup.txt").as_posix(),
                CONFIG.as_posix(),
            ],
            check=True,
            capture_output=True,
        )
        self.assertNotIn(
            "  <<: *landing_providers\n", self.config.read_text(encoding="utf-8")
        )
        self.init()
        result = self.config.read_text(encoding="utf-8")
        self.assertEqual(result.count("  <<: *landing_providers\n"), 1)
        self.assertEqual(result.count("https://subscription.invalid/personal"), 3)
        self.assertIn("家宽账号", yaml.safe_load(result)["proxy-providers"])
        self.init()
        self.assertEqual(result, self.config.read_text(encoding="utf-8"))

    def test_keep_unmodified_legacy_config(self):
        original = LEGACY.read_bytes()
        self.config.write_bytes(original)
        self.init()
        self.assertEqual(self.config.read_bytes(), original)
        self.assertTrue((self.root / "clash/private/landing.yaml").is_file())

    def test_core_capability_check(self):
        env = dict(os.environ, TMPDIR=self.root.as_posix())
        subprocess.run(
            [SHELL, HELPER.as_posix(), "check-core", Path(MIHOMO).as_posix()],
            check=True,
            capture_output=True,
            env=env,
        )
        incompatible = self.root / "old-core"
        write(incompatible, "#!/bin/sh\nexit 1\n")
        incompatible.chmod(0o755)
        result = subprocess.run(
            [SHELL, HELPER.as_posix(), "check-core", incompatible.as_posix()],
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(list(self.root.glob("surfing-landing.*")))

    def test_conflicting_merge_does_not_corrupt_config(self):
        original = self.config.read_text(encoding="utf-8").replace(
            "  <<: *landing_providers", "  <<: *personal_providers"
        )
        write(self.config, original)
        with self.assertRaises(subprocess.CalledProcessError):
            self.init()
        self.assertEqual(self.config.read_text(encoding="utf-8"), original)
        self.assertFalse(list(self.config.parent.glob("config.yaml.landing.*")))

    def test_private_files_excluded_from_recursive_permissions(self):
        self.init()
        write(self.root / "clash/.hidden", "ordinary")
        write(self.root / ".hidden", "ordinary")
        installer = (REPO / "customize.sh").read_text(encoding="utf-8")
        function = installer.split("set_box_permissions() {", 1)[1].split("\n}\n", 1)[0]
        harness = self.root / "permissions.sh"
        write(
            harness,
            "BOX_BLL_PATH=$1\n"
            'set_perm() { printf "single %s\\n" "$1"; }\n'
            'set_perm_recursive() { printf "recursive %s\\n" "$1"; }\n'
            "set_box_permissions() {" + function + "\n}\nset_box_permissions\n",
        )
        result = subprocess.check_output(
            [SHELL, harness.as_posix(), self.root.as_posix()]
        ).decode()
        self.assertNotIn("private", result)
        self.assertNotIn("recursive " + self.root.as_posix() + "\n", result)
        self.assertNotIn("recursive " + self.root.as_posix() + "/clash\n", result)
        self.assertIn("/clash/.hidden", result)
        self.assertIn("recursive " + self.root.as_posix() + "/.hidden", result)

    def test_custom_provider_indentation(self):
        for width in (2, 4, 8):
            with self.subTest(indent=width):
                indent = " " * width
                original = (
                    "landing-providers: &landing_providers\n"
                    "  家宽账号: {type: file, path: ./private/landing.yaml}\n"
                    "proxy-providers:\n"
                    "  # A user-formatted subscription block.\n"
                    + indent
                    + "personal: {type: inline, payload: []}\n"
                    + "profile: {store-selected: true}\n"
                )
                write(self.config, original)
                self.init()
                result = self.config.read_text(encoding="utf-8")
                providers = yaml.safe_load(result)["proxy-providers"]
                self.assertEqual(set(providers), {"家宽账号", "personal"})
                self.assertIn(indent + "<<: *landing_providers\n", result)
                self.init()
                self.assertEqual(self.config.read_text(encoding="utf-8"), result)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        if not BUSYBOX:
            self.skipTest("pass --busybox to run installer integration tests")
        self.temp = tempfile.TemporaryDirectory(prefix="surfing-installer-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.box = self.root / "data/adb/box_bll"
        self.stage = self.root / "module-update"
        self.account = self.box / "clash/private/landing.yaml"

    def stage_module(self):
        self.stage.mkdir(exist_ok=True)
        (self.stage / "box_bll/bin").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BUSYBOX, self.stage / "box_bll/bin/busybox")
        shutil.copyfile(MIHOMO, self.stage / "box_bll/bin/clash")
        write(self.stage / "box_bll/bin/curl", "fixture")
        for relative in (
            "clash/config.yaml",
            "clash/landing.example.yaml",
            "clash/preferred.example.json",
            "scripts/box.landing",
            "scripts/box.preferred",
            "scripts/box.preferred.json.awk",
            "scripts/box.preferred.policy.awk",
            "scripts/box.config",
            "clash/etc/hosts",
        ):
            target = self.stage / "box_bll" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / "box_bll" / relative, target)
        (self.stage / "box_bll/clash/proxies").mkdir(exist_ok=True)
        for source in (REPO / "box_bll/clash/rules").glob("AI-*.list"):
            target = self.stage / "box_bll/clash/rules" / source.name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target)
        write(self.stage / "Surfing_service.sh", "# fixture service\n")
        shutil.copyfile(REPO / "module.prop", self.stage / "module.prop")

    def install(self, keep=False, success=True, fail_ai_copy=False):
        self.stage_module()
        installer = (REPO / "customize.sh").read_text(encoding="utf-8")
        installer = installer.replace("/data/", self.root.as_posix() + "/data/")
        # Host cannot install Android BusyBox applet symlinks; all migration/deployment
        # logic and the new helper still run, using the supplied host BusyBox/core.
        original = next(
            line
            for line in installer.splitlines()
            if line.startswith("init_busybox_toolchain()")
        )
        installer = installer.replace(original, "init_busybox_toolchain() { :; }")
        if fail_ai_copy:
            # Inject a partial write followed by a copy error (such as ENOSPC).
            # Leave all other real BusyBox filesystem operations unchanged.
            installer = (
                """cp() {
  if [ "$1" = "-f" ] && [ "${2##*/}" = "AI-Gemini.list" ]; then
    destination="$3"
    [ ! -d "$destination" ] || destination="$destination/AI-Gemini.list"
    printf 'partial-copy\\n' > "$destination"
    return 1
  fi
  command cp "$@"
}
"""
                + installer
            )
        script = self.root / "customize-host.sh"
        write(script, installer)
        write(self.root / "key-index", "0\n")
        write(
            self.root / "keys",
            "KEY_VOLUMEDOWN\nKEY_VOLUMEDOWN\n"
            + ("KEY_VOLUMEUP\n" if keep else "KEY_VOLUMEDOWN\n"),
        )
        env = dict(
            os.environ,
            BOOTMODE="true",
            KSU="false",
            MODPATH=self.stage.as_posix(),
            ZIPFILE="unused",
            TMPDIR=self.root.as_posix(),
            INSTALLER=script.as_posix(),
            KEY_INDEX=(self.root / "key-index").as_posix(),
            KEYS=(self.root / "keys").as_posix(),
            PERM_LOG=(self.root / "permissions.log").as_posix(),
        )
        result = subprocess.run(
            [SHELL, (REPO / "tests/installer-harness.sh").as_posix()],
            cwd=self.root,
            env=env,
            capture_output=True,
            check=False,
            timeout=30,
        )
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        if success:
            self.assertEqual(result.returncode, 0, output)
            self.assertNotIn("Permission denied", output)
            self.assertNotRegex(output, r": (?:.*: )?not found\b")
        else:
            self.assertNotEqual(result.returncode, 0, output)
        return output

    def test_first_install_upgrade_and_keep_config(self):
        self.install()
        self.assertEqual(self.account.read_bytes(), EXAMPLE.read_bytes())
        preferred = self.box / "clash/private/preferred.json"
        defaults = json.loads(preferred.read_text(encoding="utf-8"))
        self.assertFalse(defaults["enabled"])
        self.assertEqual(defaults["reputation_provider"], "proxycheck")
        self.assertEqual(defaults["proxycheck_key"], "")
        # Simulate a deployed configuration from before provider selection existed.
        for key in ("reputation_provider", "proxycheck_key", "proxycheck_max_risk"):
            defaults.pop(key)
        defaults.update(
            {"enabled": True, "api_key": "fixture-private-key", "daily_budget": 37}
        )
        personal_preferred = json.dumps(defaults)
        write(preferred, personal_preferred)
        ledger = self.box / "clash/private/preferred/ips"
        write(ledger, "198.51.100.1\t1\tSG\t10\t0\n")
        self.assertEqual(
            (self.box / "scripts/box.landing").read_bytes(), HELPER.read_bytes()
        )
        self.assertTrue((self.stage / "default_config.yaml").is_file())
        personal = "proxies:\n  - {name: personal, type: reject}\n"
        write(self.account, personal)
        config = self.box / "clash/config.yaml"
        original = config.read_text(encoding="utf-8") + "# personal-marker\n"
        write(config, original)
        self.install(keep=True)
        self.assertEqual(config.read_text(encoding="utf-8"), original)
        self.assertEqual(self.account.read_text(encoding="utf-8"), personal)
        self.assertEqual(preferred.read_text(encoding="utf-8"), personal_preferred)
        self.assertIn("198.51.100.1", ledger.read_text())
        self.install(keep=False)
        self.assertEqual(self.account.read_text(encoding="utf-8"), personal)
        self.assertEqual(preferred.read_text(encoding="utf-8"), personal_preferred)
        self.assertIn("198.51.100.1", ledger.read_text())
        self.assertNotIn("# personal-marker", config.read_text(encoding="utf-8"))

    def test_missing_preferred_helper_preserves_existing_config(self):
        self.install()
        config = self.box / "clash/config.yaml"
        original = config.read_bytes()
        stage = self.stage_module

        def missing_helper():
            stage()
            (self.stage / "box_bll/scripts/box.preferred.policy.awk").unlink()

        self.stage_module = missing_helper
        output = self.install(success=False)
        self.assertIn("Missing preferred-mode file", output)
        self.assertEqual(config.read_bytes(), original)
        self.assertIn(
            "家宽账号",
            yaml.safe_load(config.read_text(encoding="utf-8"))["proxy-providers"],
        )
        log = (self.root / "permissions.log").read_text(encoding="utf-8")
        for line in log.splitlines():
            if "/private" in line:
                self.assertTrue(line.startswith("single "), line)
                self.assertTrue(line.endswith((" 0600", " 0700")), line)

    def test_legacy_upgrade_choices(self):
        self.install()
        self.account.unlink()
        config = self.box / "clash/config.yaml"
        original = LEGACY.read_text(encoding="utf-8").replace(
            "此处引入您的Clash订阅链接地址", "https://subscription.invalid/personal"
        )
        write(config, original)
        self.install(keep=True)
        self.assertEqual(config.read_text(encoding="utf-8"), original)
        self.assertEqual(self.account.read_bytes(), EXAMPLE.read_bytes())
        self.install(keep=False)
        text = config.read_text(encoding="utf-8")
        self.assertEqual(text.count("https://subscription.invalid/personal"), 3)
        self.assertEqual(text.count("  <<: *landing_providers\n"), 1)
        self.assertIn("家宽账号", yaml.safe_load(text)["proxy-providers"])

    def test_ai_rules_deployed_and_personal_files_preserved(self):
        defaults = list((REPO / "box_bll/clash/rules").glob("AI-*.list"))
        self.assertEqual(len(defaults), 10)
        self.install()
        rules = self.box / "clash/rules"
        for source in defaults:
            self.assertEqual((rules / source.name).read_bytes(), source.read_bytes())
            (rules / source.name).unlink()  # Simulate a pre-AI installation.
        personal = {
            rules / "OpenAI.mrs": b"old-remote-rule-cache",
            rules / "personal.list": b"DOMAIN,personal.invalid\n",
            self.box / "clash/etc/AI-user.list": b"DOMAIN,user.invalid\n",
            self.box / "clash/cache.db": b"existing-selection-cache",
        }
        for path, content in personal.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        config = self.box / "clash/config.yaml"
        config.write_bytes(LEGACY.read_bytes())
        for keep in (True, False, False):
            with self.subTest(keep=keep):
                self.install(keep=keep)
                for source in defaults:
                    self.assertEqual(
                        (rules / source.name).read_bytes(), source.read_bytes()
                    )
                for path, content in personal.items():
                    self.assertEqual(path.read_bytes(), content)
                groups = {
                    group["name"]
                    for group in yaml.safe_load(config.read_bytes())["proxy-groups"]
                }
                self.assertEqual("Gemini" in groups, not keep)
                if keep:
                    self.assertEqual(config.read_bytes(), LEGACY.read_bytes())
                for source in defaults:
                    write(rules / source.name, "# stale module defaults\n")

    def test_missing_ai_rule_aborts_before_replacing_device_files(self):
        self.install()
        config = self.box / "clash/config.yaml"
        original = config.read_bytes()
        stage = self.stage_module

        def missing_rule():
            stage()
            (self.stage / "box_bll/clash/rules/AI-Gemini.list").unlink()

        self.stage_module = missing_rule
        output = self.install(success=False)
        self.assertIn("Missing AI rule file: AI-Gemini.list", output)
        self.assertEqual(config.read_bytes(), original)
        self.assertFalse((self.box / "clash/config.yaml.bak").exists())

    def test_ai_rule_copy_failure_preserves_previous_config(self):
        self.install()
        config = self.box / "clash/config.yaml"
        config.write_bytes(LEGACY.read_bytes())
        blocked = self.box / "clash/rules/AI-Gemini.list"
        blocked.unlink()
        blocked.mkdir()  # Reject an unusable destination before replacing YAML.
        output = self.install(success=False)
        self.assertIn("Cannot deploy AI rule file: AI-Gemini.list", output)
        self.assertEqual(config.read_bytes(), LEGACY.read_bytes())
        self.assertFalse((self.box / "clash/config.yaml.bak").exists())

    def test_partial_ai_rule_copy_preserves_existing_rule(self):
        self.install()
        config = self.box / "clash/config.yaml"
        original = config.read_bytes()
        rule = self.box / "clash/rules/AI-Gemini.list"
        previous = rule.read_bytes()
        output = self.install(success=False, fail_ai_copy=True)
        self.assertIn("Cannot deploy AI rule file: AI-Gemini.list", output)
        self.assertEqual(rule.read_bytes(), previous)
        self.assertEqual(config.read_bytes(), original)
        self.assertFalse((self.box / "clash/config.yaml.bak").exists())
        self.assertEqual(list(rule.parent.glob(".AI-*")), [])

    def test_old_core_aborts_before_replacing_device_files(self):
        self.install()
        config = self.box / "clash/config.yaml"
        original = config.read_bytes()
        write(self.box / "bin/clash", "#!/bin/sh\nexit 1\n")
        output = self.install(success=False)
        self.assertIn("Update mihomo before installing", output)
        self.assertEqual(config.read_bytes(), original)
        self.assertFalse((self.box / "clash/config.yaml.bak").exists())


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="surfing-landing-core-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.front_a = server(Server, SocksHandler)
        self.front_b = server(Server, SocksHandler)
        self.landing = server(Server, SocksHandler, auth=True)
        self.web = server(Server, WebHandler)
        self.udp = server(socketserver.ThreadingUDPServer, UdpHandler)
        for instance in (self.front_a, self.front_b, self.landing, self.web, self.udp):
            self.addCleanup(instance.server_close)
            self.addCleanup(instance.shutdown)
        self.mixed, self.api_port = free_port(), free_port()
        self.cfg = copy.deepcopy(yaml.safe_load(CONFIG.read_text(encoding="utf-8")))
        self.cfg.update(
            {
                "mixed-port": self.mixed,
                "redir-port": 0,
                "tproxy-port": 0,
                "external-controller": f"127.0.0.1:{self.api_port}",
                "secret": "fixture-api",
                "allow-lan": False,
                "log-level": "debug",
                "find-process-mode": "off",
                "geo-auto-update": False,
                "hosts": {"landing.test": "127.0.0.1"},
            }
        )
        self.cfg["dns"] = {"enable": False}
        self.cfg["sniffer"] = {"enable": False}
        self.cfg["tun"] = {"enable": False}
        for listener in self.cfg.get("listeners", []):
            listener["port"] = free_port()
        for group in self.cfg["proxy-groups"]:
            if "url" in group or group["type"] in (
                "url-test",
                "fallback",
                "load-balance",
            ):
                # Include select groups such as 特殊地址: their URL also triggers
                # health checks. An unavailable loopback port keeps checks offline.
                group["url"] = "http://127.0.0.1:1/health-check"
        for key in ("external-ui", "external-ui-url", "geox-url"):
            self.cfg.pop(key, None)
        self.cfg["profile"] = {"store-selected": True}
        for i, name in enumerate(("1.主要地址", "2.备用地址", "3.额外地址")):
            front = self.front_a if i != 1 else self.front_b
            self.cfg["proxy-providers"][name] = {
                "type": "inline",
                "payload": [
                    {
                        "name": f"前置{i}",
                        "type": "socks5",
                        "server": "127.0.0.1",
                        "port": front.server_address[1],
                        "udp": False,
                    }
                ],
            }
        # Use the actual repository rules with local equivalents of remote rule data.
        for i, (name, value) in enumerate(self.cfg["rule-providers"].items()):
            behavior = value["behavior"]
            item = "198.51.100.0/24" if behavior == "ipcidr" else f"unused-{i}.invalid"
            if name == "OpenAI_域":
                item = "landing.test"
            if behavior == "classical":
                item = "DOMAIN," + item
            rule_file = self.root / "rules" / f"{i}.txt"
            write(rule_file, item + "\n")
            self.cfg["rule-providers"][name] = {
                "type": "file",
                "behavior": behavior,
                "format": "text",
                "path": f"./rules/{i}.txt",
            }
        self.account = self.root / "private/landing.yaml"
        self.set_account()
        self.process = None
        self.addCleanup(self.stop)

    def set_account(self, password="fixture-password", **overrides):
        proxy = {
            "name": "家宽 SOCKS5",
            "type": "socks5",
            "server": "127.0.0.1",
            "port": self.landing.server_address[1],
            "username": "fixture-user",
            "password": password,
            "udp": False,
        }
        proxy.update(overrides)
        write(self.account, yaml.safe_dump({"proxies": [proxy]}, allow_unicode=True))

    def api(self, path, method="GET", data=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.api_port}" + path,
            data=json.dumps(data).encode() if data is not None else None,
            method=method,
            headers={
                "Authorization": "Bearer fixture-api",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=3
        ) as response:
            body = response.read()
            return json.loads(body) if body else None

    def choose(self, group, proxy):
        self.api(
            "/proxies/" + urllib.parse.quote(group, safe=""), "PUT", {"name": proxy}
        )

    def start(self, select_routes=True):
        write(
            self.root / "config.yaml",
            yaml.safe_dump(self.cfg, allow_unicode=True, sort_keys=False),
        )
        result = subprocess.run(
            [MIHOMO, "-t", "-d", str(self.root)],
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout.decode(errors="replace"))
        with open(self.root / "core.log", "ab") as log:
            self.process = subprocess.Popen(
                [MIHOMO, "-d", str(self.root)], stdout=log, stderr=log
            )
        for _ in range(60):
            if self.process.poll() is not None:
                self.fail(
                    (self.root / "core.log").read_text(
                        encoding="utf-8", errors="replace"
                    )
                )
            try:
                self.api("/version")
                break
            except OSError:
                time.sleep(0.1)
        else:
            self.fail("core did not start")
        if select_routes:
            self.choose("落地前置", "前置0")
            self.choose("OpenAI", "家宽落地")

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=10)
            self.process = None

    def fetch(self, host="landing.test", port=None):
        try:
            sock, _, _ = connect_socks(
                self.mixed, host, port or self.web.server_address[1]
            )
            with sock:
                sock.sendall(
                    b"GET / HTTP/1.1\r\nHost: landing.test\r\nConnection: close\r\n\r\n"
                )
                data = b""
                while chunk := sock.recv(4096):
                    data += chunk
                return b"fixture-ok" in data
        except (OSError, EOFError):
            return False

    def udp_request(self, target_host="landing.test"):
        control, host, port = connect_socks(self.mixed, "0.0.0.0", 0, command=3)
        with control, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.8)
            packet = (
                b"\x00\x00\x00"
                + address(target_host, self.udp.server_address[1])
                + b"udp-fixture"
            )
            sock.sendto(packet, ("127.0.0.1" if host == "0.0.0.0" else host, port))
            try:
                return sock.recvfrom(4096)[0].endswith(b"udp-fixture")
            except TimeoutError:
                return False

    def test_chain_front_switch_and_normal_route(self):
        self.start()
        self.assertTrue(self.fetch())
        self.assertTrue(self.front_a.requests)
        self.assertTrue(self.landing.auth_attempts[-1])
        self.assertEqual(self.front_a.requests[-1][2], self.landing.server_address[1])
        self.choose("落地前置", "前置1")
        self.assertTrue(self.fetch())
        self.assertTrue(self.front_b.requests)
        before = len(self.landing.requests)
        self.choose("OpenAI", "🌐 本机·本地直连")
        self.assertTrue(self.fetch())
        self.assertEqual(len(self.landing.requests), before)

    def test_defaults_and_selection_persistence(self):
        self.start(select_routes=False)
        groups = self.api("/proxies")["proxies"]
        self.assertEqual(groups["OpenAI"]["now"], "总模式")
        self.assertEqual(groups["落地前置"]["now"], "⛔️ 禁止·拒绝连接")
        self.assertNotIn("家宽落地", groups["落地前置"]["all"])
        self.assertNotIn("总模式", groups["落地前置"]["all"])
        self.choose("OpenAI", "家宽落地")
        self.assertFalse(self.fetch())
        self.assertEqual(self.web.requests, [])
        self.choose("落地前置", "前置1")
        self.assertTrue(self.fetch())
        self.stop()
        self.start(select_routes=False)
        groups = self.api("/proxies")["proxies"]
        self.assertEqual(groups["OpenAI"]["now"], "家宽落地")
        self.assertEqual(groups["落地前置"]["now"], "前置1")
        self.assertTrue(self.fetch())

    def test_udp_block_only_when_landing_selected(self):
        self.start()
        self.assertFalse(self.udp_request())
        self.assertEqual(self.udp.requests, [])
        self.assertEqual(self.landing.requests, [])
        self.choose("OpenAI", "🌐 本机·本地直连")
        self.assertTrue(self.udp_request())

    def test_auth_failure_does_not_fall_through(self):
        self.set_account("wrong-password")
        self.start()
        self.assertFalse(self.fetch())
        self.assertIn(False, self.landing.auth_attempts)
        self.assertEqual(self.web.requests, [])

    def test_landing_failure_does_not_fall_through(self):
        self.landing.reject = True
        self.start()
        self.assertFalse(self.fetch())
        self.assertEqual(self.web.requests, [])

    def test_missing_account_is_rejected(self):
        self.account.unlink()
        self.start()
        self.assertFalse(self.fetch())
        self.assertEqual(self.web.requests, [])
        self.assertEqual(self.front_a.requests, [])

    def test_empty_account_is_rejected(self):
        write(self.account, "proxies: []\n")
        self.start()
        self.assertFalse(self.fetch())
        self.assertEqual(self.web.requests, [])
        self.assertEqual(self.front_a.requests, [])

    def test_invalid_account_is_rejected(self):
        write(self.account, "proxies: [broken\n")
        self.start()
        self.assertFalse(self.fetch())
        self.assertEqual(self.web.requests, [])

    def test_placeholder_is_rejected(self):
        shutil.copyfile(EXAMPLE, self.account)
        self.start()
        self.assertFalse(self.fetch())
        self.assertEqual(self.web.requests, [])

    def test_front_failure_does_not_bypass(self):
        self.front_a.reject = True
        self.start()
        self.assertFalse(self.fetch())
        self.assertEqual(self.landing.requests, [])
        self.assertEqual(self.web.requests, [])
        self.assertEqual(self.front_b.requests, [])

    def test_removed_front_fails_closed(self):
        self.start()
        self.assertTrue(self.fetch())
        before = len(self.web.requests)
        self.stop()
        self.cfg["proxy-providers"]["1.主要地址"]["payload"][0]["name"] = "replacement"
        self.start(select_routes=False)
        self.assertFalse(self.fetch())
        self.assertEqual(len(self.web.requests), before)
        self.assertEqual(
            self.api("/proxies")["proxies"]["落地前置"]["now"], "⛔️ 禁止·拒绝连接"
        )

    def test_provider_override_and_account_reload(self):
        self.set_account(**{"udp": True, "dialer-proxy": "DIRECT"})
        self.start()
        self.assertTrue(self.fetch())
        self.assertTrue(self.front_a.requests)
        provider_path = "/providers/proxies/" + urllib.parse.quote("家宽账号")
        self.assertFalse(self.api(provider_path)["proxies"][0]["udp"])
        self.set_account("wrong-password")
        self.api(provider_path, "PUT")
        before = len(self.web.requests)
        self.assertFalse(self.fetch())
        self.assertEqual(len(self.web.requests), before)
        self.set_account()
        self.api(provider_path, "PUT")
        self.assertTrue(self.fetch())

    def test_ipv6_target_uses_landing(self):
        class Server6(Server):
            address_family = socket.AF_INET6

        try:
            web6 = server(Server6, WebHandler, host="::1")
        except OSError as error:
            self.skipTest(f"IPv6 loopback unavailable: {error}")
        self.addCleanup(web6.server_close)
        self.addCleanup(web6.shutdown)
        self.cfg["rules"].insert(0, "IP-CIDR6,::1/128,OpenAI,no-resolve")
        self.start()
        self.assertTrue(self.fetch("::1", web6.server_address[1]))
        self.assertEqual(self.landing.requests[-1][1], "::1")
        self.assertTrue(self.front_a.requests)

    def test_failed_refresh_keeps_last_exit_until_restart(self):
        self.start()
        self.assertTrue(self.fetch())
        self.account.unlink()
        with self.assertRaises(urllib.error.HTTPError) as result:
            self.api("/providers/proxies/" + urllib.parse.quote("家宽账号"), "PUT")
        self.assertEqual(result.exception.code, 503)
        self.assertTrue(self.fetch())
        self.assertEqual(len(self.landing.auth_attempts), 2)
        self.stop()
        self.start(select_routes=False)
        self.assertFalse(self.fetch())
        self.assertEqual(len(self.landing.auth_attempts), 2)

    def test_dns_group_excludes_rematch_and_dials_normally(self):
        dns_server = server(Server, DnsHandler)
        self.addCleanup(dns_server.server_close)
        self.addCleanup(dns_server.shutdown)
        dns_port = free_port()
        self.cfg["dns"] = {
            "enable": True,
            "listen": f"127.0.0.1:{dns_port}",
            "enhanced-mode": "redir-host",
            "ipv6": False,
            "nameserver": [f"tcp://127.0.0.1:{dns_server.server_address[1]}#DNS连接"],
        }
        self.start()
        groups = self.api("/proxies")["proxies"]
        self.assertNotIn("家宽落地", groups["DNS连接"]["all"])
        self.choose("DNS连接", "前置0")
        query = (
            b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
            b"\x07example\x07invalid\x00\x00\x01\x00\x01"
        )
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(3)
            client.sendto(query, ("127.0.0.1", dns_port))
            response = client.recv(4096)
        self.assertIn(socket.inet_aton("203.0.113.1"), response)
        self.assertTrue(dns_server.requests)
        self.assertEqual(self.front_a.requests[-1][2], dns_server.server_address[1])
        self.assertEqual(self.landing.requests, [])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mihomo", required=True)
    parser.add_argument("--shell", default="bash")
    parser.add_argument(
        "--busybox", help="host BusyBox executable for installer integration tests"
    )
    args, rest = parser.parse_known_args()
    MIHOMO, SHELL = str(Path(args.mihomo).resolve()), args.shell
    BUSYBOX = str(Path(args.busybox).resolve()) if args.busybox else None
    unittest.main(argv=[__file__, *rest], verbosity=2)

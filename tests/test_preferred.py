"""Preferred-mode checks with real BusyBox/mihomo and loopback-only fixtures.

The temporary worker replaces ONLY remote endpoint URLs and wall-clock sleeps.
No subscriptions, user API keys, public reputation services or Android devices are used.
"""

import argparse
import copy
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

import test_landing as landing
import yaml

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "box_bll/scripts"
SOURCE = yaml.safe_load((REPO / "box_bll/clash/config.yaml").read_bytes())
SHELL = BUSYBOX = MIHOMO = CURL = None
REJECT = "⛔️ 禁止·拒绝连接"
ENCODE = lambda value: urllib.parse.quote(value, safe="~")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def run_json(action, data=None, **extra):
    raw_value = extra.pop("PREFERRED_VALUE", "") if action == "encode" else None
    env = dict(os.environ, LC_ALL="C", PREFERRED_ACTION=action, **extra)
    payload = (
        raw_value
        if raw_value is not None
        else (json.dumps(data, ensure_ascii=True) if data is not None else "")
    )
    result = subprocess.run(
        [BUSYBOX, "awk", "-f", str(SCRIPTS / "box.preferred.json.awk")],
        input=payload.encode(),
        capture_output=True,
        env=env,
        check=False,
        timeout=10,
    )
    return result


class JsonTests(unittest.TestCase):
    def test_strings_and_unicode_escapes_across_parser_chunks(self):
        for size in (2018, 2020, 2021, 2022, 2030, 2048, 4068, 4096):
            secret = "x" * size + '🚀\\"tail'
            result = run_json("controller-auth", {"controller_secret": secret})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout.decode().split(" = ", 1)[1]),
                "Authorization: Bearer " + secret,
            )

    def test_unicode_names_and_json_escaping_round_trip(self):
        name = 'Main：狮城 "A"\\一 🚀 $() `;`'
        encoded = run_json("encode", PREFERRED_VALUE=name)
        self.assertEqual(encoded.returncode, 0, encoded.stderr)
        self.assertEqual(encoded.stdout.decode().strip(), ENCODE(name))
        decoded = run_json("select", PREFERRED_VALUE=ENCODE(name))
        self.assertEqual(json.loads(decoded.stdout), {"name": name})
        registry = {
            "proxies": {
                "优选·探测出口": {"type": "Selector", "all": [name, "DIRECT"]},
                name: {"type": "Socks5", "alive": True, "history": [{"delay": 10}]},
                "DIRECT": {"type": "Direct"},
            }
        }
        result = run_json("inventory", registry)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.decode().strip(), ENCODE(name) + "\t1\t10")

    def test_missing_or_wrong_typed_scores_are_not_clean(self):
        good = {
            "success": True,
            "country_code": "SG",
            "fraud_score": 10,
            "recent_abuse": False,
            "bot_status": False,
        }
        self.assertEqual(run_json("score", good).stdout.decode().strip(), "SG\t10\t0")
        for patch in (
            {"fraud_score": None},
            {"fraud_score": "0"},
            {"fraud_score": -1},
            {"fraud_score": 101},
            {"recent_abuse": None},
            {"success": "true"},
            {"success": False},
        ):
            with self.subTest(patch=patch):
                result = run_json("score", {**good, **patch})
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            run_json("score", {**good, "recent_abuse": True}).stdout.decode().strip(),
            "SG\t10\t1",
        )

    def test_duplicate_members_and_invalid_json_are_rejected(self):
        for payload in (
            b'{"enabled":true,"enabled":false}',
            b'{"api_key":"\\ud800"}',
            b'{"enabled":false} garbage',
            b'{"daily_budget":01}',
        ):
            result = subprocess.run(
                [BUSYBOX, "awk", "-f", str(SCRIPTS / "box.preferred.json.awk")],
                input=payload,
                env=dict(os.environ, PREFERRED_ACTION="settings", LC_ALL="C"),
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0, payload)

    def test_exit_address_validation_and_normalization(self):
        for address in ("127.0.0.1", "192.168.1.1", "999.2.3.4", "../../file"):
            self.assertNotEqual(
                run_json("ip", {"ip": address}, PREFERRED_FAMILY="4").returncode, 0
            )
        result = run_json("ip", {"ip": "2001:db8::1"}, PREFERRED_FAMILY="6")
        self.assertEqual(result.stdout.decode().strip(), "2001:db8:0:0:0:0:0:1")
        for address in ("::1", "fe80::1", "2001:::1", "2001:db8::x"):
            self.assertNotEqual(
                run_json("ip", {"ip": address}, PREFERRED_FAMILY="6").returncode, 0
            )

    def test_current_group_graph_does_not_activate_unused_preferences(self):
        proxies = {
            "总模式": {
                "type": "Selector",
                "all": ["DIRECT", "ALL·优选"],
                "now": "DIRECT",
            },
            "OpenAI": {
                "type": "Selector",
                "all": ["总模式", "ALL·优选"],
                "now": "总模式",
            },
            "ALL·优选": {
                "type": "Selector",
                "all": ["优选·ALL出口"],
                "now": "优选·ALL出口",
            },
            "优选·ALL出口": {"type": "Selector", "all": [REJECT], "now": REJECT},
        }
        result = run_json("groups", {"proxies": proxies}, PREFERRED_MODE="rule")
        self.assertEqual(result.stdout.decode().strip().split("\t")[-1], "0")
        proxies["OpenAI"]["now"] = "ALL·优选"
        result = run_json("groups", {"proxies": proxies}, PREFERRED_MODE="rule")
        self.assertEqual(result.stdout.decode().strip().split("\t")[-1], "1")

    def test_pace_enforces_gap_and_stop_marker(self):
        with tempfile.TemporaryDirectory(prefix="surfing-pace-") as directory:
            root = Path(directory)
            source = (SCRIPTS / "box.preferred").read_text(encoding="utf-8")
            function = re.search(r"(?ms)^pace\(\) \{.*?^\}", source)[0]
            write(root / "last-request", "98\n")
            script = root / "pace.sh"
            write(
                script,
                f'STATE="{root.as_posix()}"\nREQUEST_GAP=5\n'
                'date() { echo 100; }\nsleep() { echo "$1" > "$STATE/slept"; }\n'
                'paused() { [ -f "$STATE/stop.request" ]; }\n'
                + function
                + '\npace || exit 1\ntouch "$STATE/stop.request"\npace && exit 2\nexit 0\n',
            )
            result = subprocess.run(
                [SHELL, str(script)], check=False, capture_output=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "slept").read_text().strip(), "3")


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="surfing-preferred-state-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in (
            "box.preferred",
            "box.preferred.json.awk",
            "box.preferred.policy.awk",
        ):
            source = (SCRIPTS / name).read_text(encoding="utf-8")
            source = source.replace("/data/adb/box_bll", self.root.as_posix())
            source = source.replace(
                "/data/adb/modules/Surfing/disable",
                (self.root / "module.disabled").as_posix(),
            )
            source = source.replace(
                "/dev/tmp/wifi_bypassed", (self.root / "bypassed").as_posix()
            )
            write(self.root / "scripts" / name, source)
        write(
            self.root / "clash/preferred.example.json",
            (REPO / "box_bll/clash/preferred.example.json").read_text(encoding="utf-8"),
        )
        self.state = self.root / "clash/private/preferred"
        result = self.run_worker("init")
        self.assertEqual(result.returncode, 0, result.stderr)

    def run_worker(self, action):
        return subprocess.run(
            [SHELL, str(self.root / "scripts/box.preferred"), action],
            capture_output=True,
            timeout=10,
            check=False,
        )

    def test_manual_module_and_bypass_markers_pause_before_controller_requests(self):
        for marker in ("manual", "module.disabled", "bypassed"):
            path = self.root / marker
            write(path, "")
            result = self.run_worker("once")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Paused", (self.state / "summary").read_text())
            self.assertEqual((self.state / "quota").read_text(), "")
            path.unlink()

    def test_dead_lock_recovered_live_lock_preserved(self):
        write(self.root / "manual", "")
        owner = self.state / "work.lock/pid"
        write(owner, "99999999\n")
        self.assertEqual(self.run_worker("once").returncode, 0)
        self.assertFalse(owner.parent.exists())
        write(owner, str(os.getpid()) + "\n")
        self.assertEqual(self.run_worker("once").returncode, 0)
        self.assertEqual(owner.read_text().strip(), str(os.getpid()))

    def test_reinitialization_preserves_key_and_state(self):
        settings = self.root / "clash/private/preferred.json"
        write(settings, '{"enabled":true,"api_key":"fixture-key"}')
        write(self.state / "quota", "2026-11-07 37\n")
        self.assertEqual(self.run_worker("init").returncode, 0)
        self.assertIn("fixture-key", settings.read_text())
        self.assertEqual((self.state / "quota").read_text(), "2026-11-07 37\n")


class NodeHandler(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        sock.settimeout(5)
        try:
            version, nmethods = landing.read_exact(sock, 2)
            if version != 5:
                return
            landing.read_exact(sock, nmethods)
            sock.sendall(b"\x05\x00")
            version, command, _, kind = landing.read_exact(sock, 4)
            host = landing.read_address(sock, kind)
            port = int.from_bytes(landing.read_exact(sock, 2), "big")
            if version != 5 or command != 1 or host != "127.0.0.1":
                self.server.errors.append((host, port))
                return
            sock.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
            while True:
                request = b""
                while b"\r\n\r\n" not in request and len(request) < 65536:
                    chunk = sock.recv(4096)
                    if not chunk:
                        return
                    request += chunk
                path = request.split(b" ", 2)[1].decode()
                self.server.paths.append(path)
                if path.startswith("/delay") and getattr(
                    self.server, "delay_fail", False
                ):
                    return
                time.sleep(self.server.delay)
                if path.startswith("/ip6"):
                    body = json.dumps({"ip": self.server.ip6}).encode()
                elif path.startswith("/ip"):
                    body = json.dumps({"ip": self.server.ip4}).encode()
                else:
                    body = b""
                status = b"200 OK" if body else b"204 No Content"
                close = b"connection: close" in request.lower()
                connection = "close" if close else "keep-alive"
                sock.sendall(
                    b"HTTP/1.1 "
                    + status
                    + b"\r\nContent-Type: application/json\r\n"
                    + f"Content-Length: {len(body)}\r\nConnection: {connection}\r\n\r\n".encode()
                    + body
                )
                if close:
                    return
        except (OSError, EOFError, IndexError):
            pass


class IntelligenceHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/delay":
            self.send_response(204)
            self.end_headers()
            return
        parts = path.split("/")
        if len(parts) != 4 or parts[1] != "ip" or parts[2] != "fixture-private-key":
            self.send_error(400)
            return
        address = urllib.parse.unquote(parts[3])
        self.server.lookups.append(address)
        if self.server.limited:
            self.send_response(429)
            self.send_header("Retry-After", "3600")
            self.end_headers()
            return
        country, risk = self.server.scores.get(address, ("US", 99))
        body = json.dumps(
            {
                "success": True,
                "country_code": country,
                "fraud_score": risk,
                "recent_abuse": False,
                "bot_status": False,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class WorkerTests(unittest.TestCase):
    def serve(self, kind, handler, **attributes):
        instance = kind(("127.0.0.1", 0), handler)
        for key, value in attributes.items():
            setattr(instance, key, value)
        threading.Thread(
            target=lambda: instance.serve_forever(poll_interval=0.03), daemon=True
        ).start()
        self.addCleanup(instance.server_close)
        self.addCleanup(instance.shutdown)
        return instance

    def setUp(self):
        if not MIHOMO:
            self.skipTest("pass --mihomo and --curl for loopback runtime checks")
        self.temp = tempfile.TemporaryDirectory(prefix="surfing-preferred-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.nodes = [
            self.serve(
                landing.Server,
                NodeHandler,
                ip4=ip4,
                ip6=ip6,
                delay=delay,
                paths=[],
                errors=[],
            )
            for ip4, ip6, delay in (
                ("198.51.100.10", "2001:db8::10", 0.008),
                ("198.51.100.10", "2001:db8::10", 0.03),
                ("198.51.100.20", "2001:db8::20", 0.015),
            )
        ]
        self.names = ['A 狮城 "一"\\ 🚀', "B 香港名字但出口狮城", "C 香港"]
        self.intelligence = self.serve(
            http.server.ThreadingHTTPServer,
            IntelligenceHandler,
            lookups=[],
            limited=False,
            scores={
                "198.51.100.10": ("SG", 10),
                "198.51.100.20": ("HK", 12),
                "2001:db8:0:0:0:0:0:10": ("SG", 10),
                "2001:db8:0:0:0:0:0:20": ("HK", 12),
            },
        )
        origin = f"http://127.0.0.1:{self.intelligence.server_address[1]}"
        self.cfg = copy.deepcopy(SOURCE)
        self.api_port = landing.free_port()
        self.cfg.update(
            {
                "mixed-port": landing.free_port(),
                "redir-port": 0,
                "tproxy-port": 0,
                "external-controller": f"127.0.0.1:{self.api_port}",
                "secret": 'fixture-ctrl"\\secret',
                "mode": "rule",
                "allow-lan": False,
                "log-level": "warning",
                "geo-auto-update": False,
                "find-process-mode": "off",
            }
        )
        for key in ("external-ui", "external-ui-url", "geox-url"):
            self.cfg.pop(key, None)
        for key in ("dns", "sniffer", "tun"):
            self.cfg[key] = {"enable": False}
        self.cfg["rule-providers"] = {}
        self.cfg["rules"] = ["MATCH,总模式"]
        payload = [
            {
                "name": name,
                "type": "socks5",
                "server": "127.0.0.1",
                "port": node.server_address[1],
                "udp": False,
            }
            for name, node in zip(self.names, self.nodes)
        ]
        self.cfg["proxy-providers"] = {
            "1.主要地址": {"type": "inline", "payload": payload},
            "2.备用地址": {
                "type": "inline",
                "payload": [{"name": "unused-2", "type": "reject"}],
            },
            "3.额外地址": {
                "type": "inline",
                "payload": [{"name": "unused-3", "type": "reject"}],
            },
            "家宽账号": {
                "type": "inline",
                "payload": [{"name": "unused-home", "type": "reject"}],
            },
        }
        for listener in self.cfg["listeners"]:
            listener["port"] = landing.free_port()
        for group in self.cfg["proxy-groups"]:
            if "url" in group or group["type"] in (
                "url-test",
                "fallback",
                "load-balance",
            ):
                group["url"] = origin + "/delay"
        self.settings = json.loads(
            (REPO / "box_bll/clash/preferred.example.json").read_text(encoding="utf-8")
        )
        self.settings.update(
            {
                "enabled": True,
                "api_key": "fixture-private-key",
                "controller": f"http://127.0.0.1:{self.api_port}",
                "controller_secret": self.cfg["secret"],
                "check_ipv6": False,
                "probe_port": self.cfg["listeners"][0]["port"],
                "management_port": self.cfg["listeners"][1]["port"],
                "batch_size": 30,
            }
        )
        for name in (
            "box.preferred",
            "box.preferred.json.awk",
            "box.preferred.policy.awk",
        ):
            source = (SCRIPTS / name).read_text(encoding="utf-8")
            source = source.replace("#!/system/bin/sh", "#!/bin/sh")
            source = source.replace("/data/adb/box_bll", self.root.as_posix())
            source = source.replace(
                "https://ipqualityscore.com/api/json/ip/", origin + "/ip/"
            )
            source = source.replace("https://api.ipify.org?format=json", origin + "/ip")
            source = source.replace(
                "https://api6.ipify.org?format=json", origin + "/ip6"
            )
            source = source.replace(
                "https://www.gstatic.com/generate_204", origin + "/delay"
            )
            source = source.replace(
                "https://cp.cloudflare.com/generate_204", origin + "/delay"
            )
            source = source.replace("--proto '=https'", "--proto '=http'")
            source = source.replace(
                '[ "$elapsed" -lt "$REQUEST_GAP" ] && sleep $((REQUEST_GAP - elapsed))',
                ": # Timing is separately checked by test_pace_enforces_gap_and_stop_marker.",
            )
            write(self.root / "scripts" / name, source)
        null_adapter = (
            'for arg do\n  shift\n  [ "$arg" = /dev/null ] && arg=NUL\n  set -- "$@" "$arg"\ndone\n'
            if os.name == "nt"
            else ""
        )
        write(
            self.root / "bin/curl",
            "#!/bin/sh\n" + null_adapter + f'exec "{Path(CURL).as_posix()}" "$@"\n',
        )
        shutil.copyfile(
            REPO / "box_bll/clash/preferred.example.json",
            self.root / "preferred.example.json",
        )
        write(self.root / "clash/preferred.example.json", json.dumps(self.settings))
        self.save_settings()
        self.state = self.root / "clash/private/preferred"
        write(
            self.root / "core/config.yaml",
            yaml.safe_dump(self.cfg, allow_unicode=True, sort_keys=False),
        )
        self.core_log = self.enterContext(open(self.root / "core.log", "wb"))
        self.process = subprocess.Popen(
            [MIHOMO, "-d", str(self.root / "core")],
            stdout=self.core_log,
            stderr=self.core_log,
        )
        self.addCleanup(self.stop_core)
        for _ in range(100):
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
                time.sleep(0.05)
        else:
            self.fail("core did not start")
        self.choose("总模式", "🌐 本机·本地直连")
        self.choose("OpenAI", "ALL·优选")
        self.choose("Claude", "狮城地区·优选")
        self.choose("Linux.do", "香港地区·优选")

    def save_settings(self):
        write(self.root / "clash/private/preferred.json", json.dumps(self.settings))

    def stop_core(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=10)

    def api(self, path, method="GET", data=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.api_port}" + path,
            data=json.dumps(data).encode() if data is not None else None,
            method=method,
            headers={
                "Authorization": "Bearer " + self.cfg["secret"],
                "Content-Type": "application/json",
            },
        )
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=5
        ) as response:
            body = response.read()
            return json.loads(body) if body else None

    def choose(self, group, node):
        self.api("/proxies/" + ENCODE(group), "PUT", {"name": node})

    def current(self, code):
        return self.api("/proxies/" + ENCODE("优选·" + code + "出口"))["now"]

    def once(self, expected_code=0):
        result = subprocess.run(
            [SHELL, str(self.root / "scripts/box.preferred"), "once"],
            env=dict(os.environ, LC_ALL="C", ASH_STANDALONE="0"),
            capture_output=True,
            check=False,
            timeout=100,
        )
        events = self.state / "events.log"
        details = (result.stdout + result.stderr).decode(errors="replace")
        if events.exists():
            details += events.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, expected_code, details)
        self.assertFalse(list(self.state.glob("work.*")), details)
        self.assertNotIn("fixture-private-key", details)
        for node in self.nodes:
            self.assertEqual(node.errors, [])

    def age(self, ledger, fields, seconds, name=None):
        path = self.state / ledger
        rows = []
        for line in path.read_text().splitlines():
            parts = line.split("\t")
            if name is None or parts[0] == ENCODE(name):
                for index in fields:
                    parts[index] = str(int(time.time()) - seconds)
            rows.append("\t".join(parts))
        write(path, "\n".join(rows) + "\n")

    def test_shared_ip_reports_and_independent_region_choices(self):
        self.once()
        self.assertCountEqual(
            self.intelligence.lookups, ["198.51.100.10", "198.51.100.20"]
        )
        self.assertIn(self.current("SG"), self.names[:2])
        self.assertEqual(self.current("HK"), self.names[2])
        self.assertEqual(
            self.api("/proxies/" + ENCODE("总模式"))["now"], "🌐 本机·本地直连"
        )
        previous = {code: self.current(code) for code in ("ALL", "SG", "HK")}
        echoes = sum(
            path.startswith("/ip") for node in self.nodes for path in node.paths
        )
        self.once()
        self.assertEqual(len(self.intelligence.lookups), 2)
        self.assertEqual(
            sum(path.startswith("/ip") for node in self.nodes for path in node.paths),
            echoes,
        )
        self.assertEqual({code: self.current(code) for code in previous}, previous)
        self.choose("OpenAI", "🌐 本机·本地直连")
        self.once()
        self.assertEqual(self.current("ALL"), REJECT)
        self.assertEqual(self.current("SG"), previous["SG"])

    def test_disabled_mode_performs_no_external_probe(self):
        self.settings["enabled"] = False
        self.save_settings()
        self.once()
        self.assertEqual(self.intelligence.lookups, [])
        self.assertFalse(
            any(path.startswith("/ip") for node in self.nodes for path in node.paths)
        )
        self.assertEqual(self.current("ALL"), REJECT)

    def test_disabled_mode_accepts_config_without_probe_group(self):
        self.settings["enabled"] = False
        self.save_settings()
        self.cfg["listeners"] = []
        self.cfg["proxy-groups"] = [
            group
            for group in self.cfg["proxy-groups"]
            if group["name"] != "优选·探测出口"
        ]
        config = self.root / "core/config.yaml"
        write(config, yaml.safe_dump(self.cfg, allow_unicode=True, sort_keys=False))
        self.api("/configs", "PUT", {"path": str(config)})
        self.once()
        self.assertEqual(self.intelligence.lookups, [])
        self.assertEqual((self.state / "enabled").read_text().strip(), "false")

    def test_good_reputation_without_working_latency_check_is_not_selected(self):
        for node in self.nodes:
            node.delay_fail = True
        self.once()
        self.assertEqual(len(self.intelligence.lookups), 2)
        self.assertEqual(self.current("ALL"), REJECT)
        self.assertEqual(self.current("SG"), REJECT)
        self.assertEqual(self.current("HK"), REJECT)

    def test_incomplete_provider_snapshot_does_not_clear_current_selection(self):
        self.once()
        previous = {code: self.current(code) for code in ("ALL", "SG", "HK")}
        self.settings["providers"] = ["1.主要地址", "missing-provider"]
        self.save_settings()
        self.once(expected_code=1)
        self.assertEqual({code: self.current(code) for code in previous}, previous)
        self.assertEqual(len(self.intelligence.lookups), 2)

    def test_rate_limit_backoff_and_unknown_results(self):
        self.intelligence.limited = True
        self.once()
        self.assertEqual(len(self.intelligence.lookups), 1)
        self.assertEqual(self.current("ALL"), REJECT)
        self.assertEqual((self.state / "ips").read_text(), "")
        retry = int((self.state / "retry").read_text().split()[0])
        self.assertGreater(retry, time.time() + 3500)
        self.once()
        self.assertEqual(len(self.intelligence.lookups), 1)

    def test_daily_budget_survives_worker_restarts(self):
        self.settings["daily_budget"] = 1
        self.save_settings()
        self.once()
        self.once()
        self.assertEqual(len(self.intelligence.lookups), 1)
        self.assertEqual((self.state / "quota").read_text().split()[1], "1")
        self.assertEqual(self.current("HK"), REJECT)

    def test_reactivation_refreshes_respect_the_node_batch_limit(self):
        self.once()
        for group in ("OpenAI", "Claude", "Linux.do"):
            self.choose(group, "🌐 本机·本地直连")
        self.once()
        self.settings["batch_size"] = 1
        self.save_settings()
        self.age("nodes", (1, 6), 4000)
        self.age("ips", (1,), 8000)
        self.choose("OpenAI", "ALL·优选")
        self.choose("Claude", "狮城地区·优选")
        self.choose("Linux.do", "香港地区·优选")
        before = sum(
            path.startswith("/ip") for node in self.nodes for path in node.paths
        )
        self.once()
        after = sum(
            path.startswith("/ip") for node in self.nodes for path in node.paths
        )
        self.assertEqual(after - before, 1)

    def test_changed_exit_is_rechecked_and_rejected_when_high_risk(self):
        self.once()
        current = self.current("SG")
        index = self.names.index(current)
        self.nodes[index].ip4 = "198.51.100.30"
        self.intelligence.scores["198.51.100.30"] = ("SG", 95)
        self.age("nodes", (1, 6), 4000, current)
        self.once()
        self.assertEqual(self.intelligence.lookups.count("198.51.100.30"), 1)
        self.assertNotEqual(self.current("SG"), current)
        self.assertIn(self.current("SG"), self.names[:2])
        self.assertEqual(self.current("HK"), self.names[2])

    def test_ipv6_reputation_is_separate_and_blocks_bad_dual_stack(self):
        self.settings["check_ipv6"] = True
        self.save_settings()
        self.intelligence.scores["2001:db8:0:0:0:0:0:10"] = ("SG", 95)
        self.once()
        self.assertEqual(self.current("SG"), REJECT)
        self.assertEqual(self.current("HK"), self.names[2])
        self.assertEqual(len(self.intelligence.lookups), 4)

    def test_expired_candidate_is_refreshed_before_reactivation(self):
        self.once()
        self.age("ips", (1,), 8000)
        self.once()  # Keep currently usable exits; a full daily review is not due.
        self.assertEqual(len(self.intelligence.lookups), 2)
        self.choose("OpenAI", "🌐 本机·本地直连")
        self.once()
        self.assertEqual(self.current("ALL"), REJECT)
        self.choose("OpenAI", "ALL·优选")
        self.once()
        self.assertNotEqual(self.current("ALL"), REJECT)
        self.assertEqual(len(self.intelligence.lookups), 3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shell", required=True)
    parser.add_argument("--busybox", required=True)
    parser.add_argument("--mihomo")
    parser.add_argument("--curl")
    args, rest = parser.parse_known_args()
    SHELL, BUSYBOX, MIHOMO, CURL = args.shell, args.busybox, args.mihomo, args.curl
    if MIHOMO and not CURL:
        parser.error("--curl is required with --mihomo")
    unittest.main(argv=[__file__, *rest], verbosity=2)

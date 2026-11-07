"""Preferred-mode checks with real BusyBox/mihomo and loopback-only fixtures.

The temporary worker replaces ONLY remote endpoint URLs and wall-clock sleeps.
No subscriptions, user API keys, public reputation services or Android devices are used.
"""

import argparse
import copy
import http.server
import ipaddress
import json
import os
import re
import shutil
import socket
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


def run_snapshot(proxies, providers):
    with tempfile.TemporaryDirectory(prefix="surfing-discovery-") as directory:
        root = Path(directory)
        for name, data in (("proxies", proxies), ("providers", providers)):
            write(root / (name + ".json"), json.dumps(data, ensure_ascii=True))
        result = subprocess.run(
            [
                BUSYBOX,
                "awk",
                "-f",
                str(SCRIPTS / "box.preferred.json.awk"),
                str(root / "proxies.json"),
                str(root / "providers.json"),
            ],
            env=dict(
                os.environ,
                LC_ALL="C",
                PREFERRED_ACTION="snapshot",
                PREFERRED_MODE="rule",
                PREFERRED_WORK=root.as_posix(),
            ),
            capture_output=True,
            timeout=30,
            check=False,
        )
        names = root / "providers"
        return result, names.read_text() if names.exists() else ""


def proxycheck_result(address="198.51.100.10", country="SG", risk=50):
    return {
        "status": "ok",
        address: {
            "location": {"country_code": country},
            "detections": {
                "anonymous": True,
                "proxy": False,
                "vpn": True,
                "tor": False,
                "hosting": True,
                "scraper": False,
                "compromised": False,
                "risk": risk,
            },
            "attack_history": {},
        },
    }


def proxycheck_reply(server, path, source):
    url = urllib.parse.urlsplit(path)
    address = urllib.parse.unquote(url.path.removeprefix("/v3/"))
    key = urllib.parse.parse_qs(url.query).get("key", [""])[0]
    server.proxycheck_calls.append((source, address, key))
    callback = getattr(server, "on_proxycheck_call", None)
    if callback is not None:
        server.on_proxycheck_call = None
        callback()
    code = server.proxycheck_failure
    if source in server.proxycheck_denied:
        code = 403
    if source in server.proxycheck_limited:
        code = 429
    if code:
        return code, {"status": "denied" if code < 500 else "error"}, server.retry_after
    country, _ = server.scores.get(address, ("US", 99))
    # Emit compressed IPv6 like a real provider; the worker must match normalized addresses.
    label = str(ipaddress.ip_address(address))
    data = proxycheck_result(label, country)
    data[label].update(copy.deepcopy(server.proxycheck_overrides.get(address, {})))
    return 200, data, None


class JsonTests(unittest.TestCase):
    def test_provider_defaults_legacy_keys_and_optional_proxycheck_key(self):
        for settings, provider, has_key, risk in (
            ({}, "proxycheck", "false", "100"),
            ({"api_key": "legacy-key"}, "ipqs", "true", "74"),
            ({"proxycheck_key": "new-key"}, "proxycheck", "true", "100"),
            ({"reputation_provider": "ipqs"}, "ipqs", "false", "74"),
            (
                {"reputation_provider": "proxycheck", "api_key": "legacy-key"},
                "proxycheck",
                "false",
                "100",
            ),
        ):
            with self.subTest(settings=settings):
                result = run_json("settings", settings)
                self.assertEqual(result.returncode, 0, result.stderr)
                rows = result.stdout.decode().splitlines()
                self.assertEqual(
                    (rows[12], rows[14], rows[16]), (risk, has_key, provider)
                )
        for settings in (
            {"reputation_provider": "unknown"},
            {"proxycheck_key": True},
            {"proxycheck_max_risk": 101},
        ):
            self.assertNotEqual(run_json("settings", settings).returncode, 0)

    def test_reputation_request_uses_only_the_selected_provider_key(self):
        cases = (
            ({}, "https://proxycheck.io/v3/198.51.100.10?tag=0"),
            (
                {"proxycheck_key": 'key?"&x'},
                "https://proxycheck.io/v3/198.51.100.10?tag=0&key=key%3F%22%26x",
            ),
            (
                {"api_key": "old-key"},
                "https://ipqualityscore.com/api/json/ip/old-key/198.51.100.10?strictness=0&allow_public_access_points=true",
            ),
            (
                {"reputation_provider": "proxycheck", "api_key": "old-key"},
                "https://proxycheck.io/v3/198.51.100.10?tag=0",
            ),
        )
        for settings, url in cases:
            result = run_json(
                "reputation-request", settings, PREFERRED_IP="198.51.100.10"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout.decode().split(" = ", 1)[1]), url)

    def test_proxycheck_preserves_raw_scores_and_separates_abuse(self):
        address = "198.51.100.10"
        for risk, flags, history, bad in (
            (50, {}, {}, 0),
            (100, {"proxy": True}, {}, 0),
            (50, {}, {"login_attempt": 1}, 1),
            (50, {}, {"new_attack_type": 4}, 1),
            (100, {"compromised": True}, {}, 1),
            (75, {"scraper": True}, {}, 1),
            (75, {"tor": True}, {}, 1),
        ):
            data = proxycheck_result(risk=risk)
            data[address]["detections"].update(flags)
            data[address]["attack_history"] = history
            result = run_json(
                "score",
                data,
                PREFERRED_REPUTATION_PROVIDER="proxycheck",
                PREFERRED_IP=address,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.decode().strip(), f"SG\t{risk}\t{bad}")

    def test_proxycheck_rejects_unknown_fields_denials_and_mismatched_ip(self):
        address = "198.51.100.10"
        good = proxycheck_result()
        variants = []
        for field in ("risk", "compromised", "vpn"):
            for value in (None, "false"):
                data = copy.deepcopy(good)
                data[address]["detections"][field] = value
                variants.append(data)
            data = copy.deepcopy(good)
            del data[address]["detections"][field]
            variants.append(data)
        for history in (None, [], {"login_attempt": "0"}, {"scan": -1}):
            data = copy.deepcopy(good)
            data[address]["attack_history"] = history
            variants.append(data)
        data = copy.deepcopy(good)
        del data[address]["attack_history"]
        variants.append(data)
        variants.extend(
            [
                {**good, "status": "denied"},
                {
                    **good,
                    "status": "warning",
                    "message": "Your API Key has been disabled.",
                },
                proxycheck_result("198.51.100.99"),
                {"status": "ok"},
            ]
        )
        for data in variants:
            result = run_json(
                "score",
                data,
                PREFERRED_REPUTATION_PROVIDER="proxycheck",
                PREFERRED_IP=address,
            )
            self.assertNotEqual(result.returncode, 0, data)
            self.assertEqual(result.stdout, b"")

    def test_proxycheck_ipv6_normalization_warning_and_schema_risk_location(self):
        address = "2001:db8::10"
        wanted = "2001:db8:0:0:0:0:0:10"
        data = proxycheck_result(address)
        data["status"] = "warning"
        data["message"] = "You are within 10% of your query limit for the day."
        for top_level in (False, True):
            if top_level:
                data[address]["risk"] = data[address]["detections"].pop("risk")
            result = run_json(
                "score",
                data,
                PREFERRED_REPUTATION_PROVIDER="proxycheck",
                PREFERRED_IP=wanted,
            )
            self.assertEqual(result.stdout.decode().strip(), "SG\t50\t0", result.stderr)
        data[address]["detections"]["risk"] = 10
        self.assertNotEqual(
            run_json(
                "score",
                data,
                PREFERRED_REPUTATION_PROVIDER="proxycheck",
                PREFERRED_IP=wanted,
            ).returncode,
            0,
        )
        data[address]["detections"]["risk"] = 50
        data[wanted] = copy.deepcopy(data[address])
        self.assertNotEqual(
            run_json(
                "score",
                data,
                PREFERRED_REPUTATION_PROVIDER="proxycheck",
                PREFERRED_IP=wanted,
            ).returncode,
            0,
        )

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


class DiscoveryTests(unittest.TestCase):
    def node(self, name):
        return {
            "name": name,
            "type": "Socks5",
            "alive": True,
            "history": [{"delay": 12}],
        }

    def provider(self, name, nodes, vehicle="Inline"):
        # Deliberately put proxies before vehicleType to check member-order safety.
        return {"proxies": nodes, "vehicleType": vehicle, "name": name, "type": "Proxy"}

    def registry(self, names, landing_nodes=()):
        return {
            "proxies": {
                "优选·探测出口": {"type": "Selector", "all": names},
                "家宽·出口": {"type": "Selector", "all": list(landing_nodes)},
            }
        }

    def test_arbitrary_provider_names_and_generated_duplicates(self):
        name = '线路 "A" / 东京 🚀'
        source = '订阅 "自定义" / ?space=一'
        node = self.node(name)
        result, names = run_snapshot(
            self.registry([name, name]),
            {
                "providers": {
                    source: self.provider(source, [node]),
                    "generated": self.provider("generated", [node], "Compatible"),
                }
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.decode().splitlines(), [ENCODE(name) + "\t1\t12"]
        )
        self.assertEqual(names.strip(), ENCODE(source))

    def test_real_duplicates_and_landing_members_are_not_candidates(self):
        duplicate = self.node("same name")
        home = self.node("私有账号节点")
        normal = self.node("ordinary")
        result, _ = run_snapshot(
            self.registry(["same name", "私有账号节点", "ordinary"], ["私有账号节点"]),
            {
                "providers": {
                    "A": self.provider("A", [duplicate, normal]),
                    "B": self.provider("B", [duplicate]),
                    "renamed private source": self.provider(
                        "renamed private source", [home], "File"
                    ),
                }
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.decode().strip(), "ordinary\t1\t12")

    def test_incomplete_or_unknown_registry_is_an_error(self):
        registry = self.registry(["ordinary"])
        for providers in (
            {},
            {"providers": []},
            {"providers": {"A": {"name": "A", "type": "Proxy", "vehicleType": "HTTP"}}},
            {"providers": {"A": self.provider("wrong-name", [])}},
            {"providers": {"A": self.provider("A", [], "Unknown")}},
            {
                "providers": {
                    "A": self.provider("A", [{"name": "incomplete", "type": "Socks5"}])
                }
            },
        ):
            result, _ = run_snapshot(registry, providers)
            self.assertNotEqual(result.returncode, 0, providers)

    def test_generated_graph_does_not_consume_the_retained_node_limit(self):
        name = "ordinary"
        repeated = [{"name": "group", "type": "Selector", "all": [name] * 100}] * 2200
        result, _ = run_snapshot(
            self.registry([name]),
            {
                "providers": {
                    "actual": self.provider("actual", [self.node(name)], "HTTP"),
                    "generated": self.provider("generated", repeated, "Compatible"),
                }
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.decode().strip(), "ordinary\t1\t12")


class MigrationTests(unittest.TestCase):
    def convert(self, source):
        return subprocess.run(
            [BUSYBOX, "awk", "-f", str(SCRIPTS / "box.preferred.migrate.awk")],
            input=source.encode(),
            capture_output=True,
            check=False,
            timeout=10,
            env=dict(os.environ, LC_ALL="C"),
        )

    def test_current_defaults_are_byte_identical_and_legacy_groups_are_targeted(self):
        source = (REPO / "box_bll/clash/config.yaml").read_text(encoding="utf-8")
        self.assertEqual(self.convert(source).stdout.decode(), source)
        legacy = source.replace("    include-all-providers: true\n", "")
        legacy = legacy.replace("<<: *preferred_nodes", "<<: *A")
        result = self.convert(legacy)
        self.assertEqual(result.returncode, 0, result.stderr)
        before = yaml.safe_load(legacy)
        after = yaml.safe_load(result.stdout)
        for group in before["proxy-groups"]:
            if group["name"].startswith("优选·"):
                group["include-all-providers"] = True
        self.assertEqual(before, after)
        self.assertEqual(self.convert(result.stdout.decode()).stdout, result.stdout)

    def test_flow_groups_quoted_keys_and_multiline_sequences(self):
        item = """{name: '优选·探测出口', type: select, proxies: [REJECT], use: ['订阅, A'], filter: 'a}b,c'}"""
        cases = (
            "proxy-groups:\n  - " + item + "\n",
            "proxy-groups:\n- {name: 优选·探测出口, type: select, proxies: [REJECT], use: [provider#tag]}\n",
            "proxy-groups: [" + item + "]\n",
            "proxy-groups: [\n  "
            + item
            + ",\n  {name: ordinary, type: select, proxies: [DIRECT]}]\n",
            "'proxy-groups':\n- type: select\n  'name': '优选·ALL出口'\n  proxies: [REJECT]\n  include-all-providers: false\n",
            'proxy-groups:\n- {"name": "优选·SG出口", "include-all-providers": false, type: select, proxies: [REJECT]}\n',
            'proxy-groups:\n- name: "\\u4f18\\u9009\\u00b7ALL\\u51fa\\u53e3"\n  type: select\n  proxies: [REJECT]\n',
        )
        for source in cases:
            with self.subTest(source=source):
                result = self.convert(source)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = yaml.safe_load(source)
                for group in expected["proxy-groups"]:
                    if group["name"].startswith("优选·"):
                        group["include-all-providers"] = True
                self.assertEqual(yaml.safe_load(result.stdout), expected)
                self.assertEqual(
                    self.convert(result.stdout.decode()).stdout, result.stdout
                )
        self.assertEqual(
            self.convert("proxy-groups: []\n").stdout, b"proxy-groups: []\n"
        )

    def test_duplicate_preferred_groups_are_rejected(self):
        source = "proxy-groups:\n- name: 优选·ALL出口\n  proxies: [REJECT]\n" * 2
        self.assertNotEqual(self.convert(source).returncode, 0)

    def run_migration(self, root):
        return subprocess.run(
            [
                SHELL,
                str(SCRIPTS / "box.preferred.migrate"),
                str(root),
                str(root / "clash/config.yaml"),
                MIHOMO,
            ],
            capture_output=True,
            check=False,
            timeout=20,
        )

    def fixture(self):
        return {
            "mode": "rule",
            "rules": ["MATCH,DIRECT"],
            "proxy-providers": {
                "任意订阅 / 当前名称": {
                    "type": "inline",
                    "payload": [
                        {
                            "name": "fixture-node",
                            "type": "socks5",
                            "server": "127.0.0.1",
                            "port": 9,
                        }
                    ],
                }
            },
            "proxy-groups": [
                {
                    "name": "优选·探测出口",
                    "type": "select",
                    "proxies": ["REJECT"],
                    "use": ["old-provider-name"],
                },
                {
                    "name": "优选·ALL出口",
                    "type": "select",
                    "proxies": ["REJECT"],
                    "use": ["old-provider-name"],
                },
                {
                    "name": "personal group",
                    "type": "select",
                    "proxies": ["DIRECT"],
                    "include-all-providers": False,
                },
            ],
        }

    def test_core_checked_migration_preserves_backup_and_private_settings(self):
        if not MIHOMO:
            self.skipTest("pass --mihomo for migration validation")
        with tempfile.TemporaryDirectory(
            prefix="surfing-preferred-migration-"
        ) as directory:
            root = Path(directory)
            config = root / "clash/config.yaml"
            source = yaml.safe_dump(self.fixture(), allow_unicode=True, sort_keys=False)
            write(config, source)
            private = root / "clash/private/preferred.json"
            personal = '{"enabled": true, "api_key": "fixture-only", "providers": ["old"], "daily_budget": 37}\n'
            write(private, personal)
            result = self.run_migration(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                config.with_suffix(".yaml.preferred.bak").read_text(encoding="utf-8"),
                source,
            )
            self.assertEqual(private.read_text(), personal)
            migrated = config.read_bytes()
            result = self.run_migration(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(config.read_bytes(), migrated)
            self.assertFalse(list(config.parent.glob("*.preferred-check.*")))

    def test_failed_core_check_keeps_original_config(self):
        if not MIHOMO:
            self.skipTest("pass --mihomo for migration validation")
        with tempfile.TemporaryDirectory(
            prefix="surfing-preferred-migration-"
        ) as directory:
            root = Path(directory)
            fixture = self.fixture()
            fixture["mixed-port"] = "invalid-port"
            config = root / "clash/config.yaml"
            source = yaml.safe_dump(fixture, allow_unicode=True, sort_keys=False)
            write(config, source)
            result = self.run_migration(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(config.read_text(encoding="utf-8"), source)
            self.assertFalse(config.with_suffix(".yaml.preferred.bak").exists())


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
        controller_guard = socket.socket()
        controller_guard.bind(("127.0.0.1", 0))
        self.addCleanup(controller_guard.close)
        defaults = json.loads(
            (REPO / "box_bll/clash/preferred.example.json").read_text(encoding="utf-8")
        )
        defaults["controller"] = f"http://127.0.0.1:{controller_guard.getsockname()[1]}"
        write(self.root / "clash/preferred.example.json", json.dumps(defaults))
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
                response_code = 200
                retry_after = None
                if path.startswith("/v3/"):
                    if (
                        self.server.ip4
                        in self.server.intelligence.proxycheck_disconnect
                    ):
                        return
                    response_code, data, retry_after = proxycheck_reply(
                        self.server.intelligence, path, self.server.ip4
                    )
                    body = json.dumps(data).encode()
                elif path.startswith("/ip6"):
                    body = json.dumps({"ip": self.server.ip6}).encode()
                elif path.startswith("/ip"):
                    body = json.dumps({"ip": self.server.ip4}).encode()
                else:
                    body = b""
                status = (
                    f"{response_code} Response".encode() if body else b"204 No Content"
                )
                close = b"connection: close" in request.lower()
                connection = "close" if close else "keep-alive"
                headers = (
                    b"HTTP/1.1 "
                    + status
                    + b"\r\nContent-Type: application/json\r\n"
                    + f"Content-Length: {len(body)}\r\nConnection: {connection}\r\n".encode()
                )
                if retry_after is not None:
                    headers += f"Retry-After: {retry_after}\r\n".encode()
                sock.sendall(headers + b"\r\n" + body)
                if close:
                    return
        except (OSError, EOFError, IndexError):
            pass


class IntelligenceHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path.startswith("/v3/"):
            code, data, retry_after = proxycheck_reply(
                self.server, self.path, "management"
            )
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if retry_after is not None:
                self.send_header("Retry-After", str(retry_after))
            self.end_headers()
            self.wfile.write(body)
            return
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


class SnapshotControllerHandler(http.server.BaseHTTPRequestHandler):
    """Real HTTP boundary for unavailable/incomplete discovery responses."""

    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.server.calls.append(("GET", self.path))
        if self.path == "/providers/proxies":
            code, payload = self.server.response_status, self.server.response_body
        else:
            request = urllib.request.Request(
                self.server.upstream + self.path,
                headers={"Authorization": self.headers.get("Authorization", "")},
            )
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                request, timeout=5
            ) as response:
                code, payload = response.status, response.read()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_PUT(self):
        self.server.calls.append(("PUT", self.path))
        self.send_error(405)


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
            proxycheck_calls=[],
            proxycheck_failure=0,
            proxycheck_denied=set(),
            proxycheck_limited=set(),
            proxycheck_disconnect=set(),
            proxycheck_overrides={},
            retry_after=3600,
            scores={
                "198.51.100.10": ("SG", 10),
                "198.51.100.20": ("HK", 12),
                "2001:db8:0:0:0:0:0:10": ("SG", 10),
                "2001:db8:0:0:0:0:0:20": ("HK", 12),
            },
        )
        for node in self.nodes:
            node.intelligence = self.intelligence
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
                "reputation_provider": "ipqs",
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
            source = source.replace("https://proxycheck.io/v3/", origin + "/v3/")
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

    def reload_config(self):
        config = self.root / "core/config.yaml"
        write(config, yaml.safe_dump(self.cfg, allow_unicode=True, sort_keys=False))
        self.api("/configs", "PUT", {"path": str(config)})
        self.choose("总模式", "🌐 本机·本地直连")
        self.choose("OpenAI", "ALL·优选")
        self.choose("Claude", "狮城地区·优选")
        self.choose("Linux.do", "香港地区·优选")

    def rename_providers(self, names):
        self.cfg["proxy-providers"] = {
            names.get(name, name): provider
            for name, provider in self.cfg["proxy-providers"].items()
        }
        # The ordinary user config must still be valid. Preferred groups have
        # no per-provider use list to edit: they follow include-all-providers.
        for group in self.cfg["proxy-groups"]:
            if "use" in group:
                group["use"] = [names.get(name, name) for name in group["use"]]
        self.reload_config()

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
        self.assertNotIn("fixture-proxycheck-key", details)
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

    def use_proxycheck(self, key=""):
        self.settings.update(
            {"reputation_provider": "proxycheck", "proxycheck_key": key}
        )
        self.save_settings()

    def test_proxycheck_keyless_queries_each_exit_and_shares_reports(self):
        self.use_proxycheck()
        self.once()
        self.assertEqual(self.intelligence.lookups, [])
        self.assertCountEqual(
            self.intelligence.proxycheck_calls,
            [
                ("198.51.100.10", "198.51.100.10", ""),
                ("198.51.100.20", "198.51.100.20", ""),
            ],
        )
        self.assertEqual((self.state / "ips").read_text(), "")
        self.assertEqual(
            len((self.state / "ips.proxycheck").read_text().splitlines()), 2
        )
        previous = {code: self.current(code) for code in ("ALL", "SG", "HK")}
        self.assertIn(previous["SG"], self.names[:2])
        self.assertEqual(previous["HK"], self.names[2])
        self.once()
        self.assertEqual(len(self.intelligence.proxycheck_calls), 2)
        self.assertEqual({code: self.current(code) for code in previous}, previous)
        self.assertIn("proxycheck", (self.state / "report.tsv").read_text())
        self.assertEqual(
            self.api("/proxies/" + ENCODE("总模式"))["now"], "🌐 本机·本地直连"
        )

    def test_one_pass_uses_consistent_provider_credentials_and_route(self):
        self.use_proxycheck()

        def change_provider():
            self.settings["reputation_provider"] = "ipqs"
            self.save_settings()

        self.intelligence.on_proxycheck_call = change_provider
        self.once()
        self.assertEqual(len(self.intelligence.proxycheck_calls), 2)
        self.assertTrue(
            all(
                source == address and not key
                for source, address, key in self.intelligence.proxycheck_calls
            )
        )
        self.assertIn(self.current("SG"), self.names[:2])
        self.once()
        self.assertEqual(len(self.intelligence.lookups), 2)
        self.assertEqual(len(self.intelligence.proxycheck_calls), 2)

    def test_proxycheck_exit_denial_is_unknown_and_does_not_retry_via_another_node(
        self,
    ):
        self.use_proxycheck()
        self.intelligence.proxycheck_denied.add("198.51.100.10")
        self.once()
        self.assertCountEqual(
            self.intelligence.proxycheck_calls,
            [
                ("198.51.100.10", "198.51.100.10", ""),
                ("198.51.100.20", "198.51.100.20", ""),
            ],
        )
        self.assertEqual(self.current("SG"), REJECT)
        self.assertEqual(self.current("HK"), self.names[2])
        self.assertNotIn("198.51.100.10", (self.state / "ips.proxycheck").read_text())
        retry = (self.state / "retry.proxycheck-exits").read_text().splitlines()
        blocked = next(
            line.split("\t") for line in retry if line.startswith("198.51.100.10\t")
        )
        self.assertGreater(int(blocked[1]), time.time() + 3500)
        self.age("nodes", (1, 6), 2000)
        self.once()
        self.assertEqual(len(self.intelligence.proxycheck_calls), 2)
        self.assertIn("stay unknown", (self.state / "events.log").read_text())

    def test_proxycheck_exit_backoff_increases_and_survives_other_exit_success(self):
        self.use_proxycheck()
        self.intelligence.proxycheck_limited.add("198.51.100.10")
        self.intelligence.retry_after = None
        for count, wait in ((1, 900), (2, 3600), (3, 21600)):
            if count > 1:
                self.age("nodes", (1, 6), 2000)
                self.age("retry.proxycheck-exits", (1,), 1, "198.51.100.10")
            self.once()
            entries = (self.state / "retry.proxycheck-exits").read_text().splitlines()
            blocked = next(
                line.split("\t")
                for line in entries
                if line.startswith("198.51.100.10\t")
            )
            self.assertEqual(int(blocked[2]), count)
            self.assertGreater(int(blocked[1]), time.time() + wait - 100)
        calls = [
            call
            for call in self.intelligence.proxycheck_calls
            if call[0] == "198.51.100.10"
        ]
        self.assertEqual(len(calls), 3)

    def test_proxycheck_key_uses_management_route_without_anonymous_fallback(self):
        self.use_proxycheck("fixture-proxycheck-key")
        self.once()
        self.assertCountEqual(
            self.intelligence.proxycheck_calls,
            [
                ("management", "198.51.100.10", "fixture-proxycheck-key"),
                ("management", "198.51.100.20", "fixture-proxycheck-key"),
            ],
        )
        self.assertFalse(
            any(path.startswith("/v3/") for node in self.nodes for path in node.paths)
        )
        previous = {code: self.current(code) for code in ("ALL", "SG", "HK")}
        self.intelligence.proxycheck_failure = 401
        self.age("nodes", (1, 6), 4000)
        self.age("ips.proxycheck", (1,), 90000)
        self.once()
        self.assertEqual(len(self.intelligence.proxycheck_calls), 3)
        self.assertTrue(
            all(
                call[0] == "management" and call[2]
                for call in self.intelligence.proxycheck_calls
            )
        )
        self.assertEqual({code: self.current(code) for code in previous}, previous)

    def test_proxycheck_outage_pauses_service_and_does_not_create_clean_reports(self):
        self.use_proxycheck()
        self.intelligence.proxycheck_failure = 503
        self.once()
        self.assertEqual(len(self.intelligence.proxycheck_calls), 1)
        self.assertEqual((self.state / "ips.proxycheck").read_text(), "")
        self.assertEqual(self.current("ALL"), REJECT)
        self.once()
        self.assertEqual(len(self.intelligence.proxycheck_calls), 1)

    def test_transport_failure_does_not_reuse_a_previous_denial_response(self):
        self.use_proxycheck()
        self.intelligence.proxycheck_denied.add("198.51.100.10")
        self.intelligence.proxycheck_disconnect.add("198.51.100.20")
        self.once()
        until, count = (self.state / "retry.proxycheck").read_text().split()
        self.assertEqual(count, "1")
        self.assertGreater(int(until), time.time() + 800)
        self.assertNotIn(
            "198.51.100.20", (self.state / "retry.proxycheck-exits").read_text()
        )
        self.assertIn("HTTP 000", (self.state / "lookup-status").read_text())
        self.assertEqual((self.state / "quota").read_text().split()[1], "2")
        self.assertEqual((self.state / "ips.proxycheck").read_text(), "")
        self.assertEqual(self.current("ALL"), REJECT)
        self.once()
        self.assertEqual(len(self.intelligence.proxycheck_calls), 1)

    def test_proxycheck_unknown_history_cannot_be_selected(self):
        self.use_proxycheck()
        self.intelligence.proxycheck_overrides = {
            address: {"attack_history": None}
            for address in ("198.51.100.10", "198.51.100.20")
        }
        self.once()
        self.assertEqual(self.current("ALL"), REJECT)
        self.assertEqual((self.state / "ips.proxycheck").read_text(), "")

    def test_proxycheck_expired_candidate_refreshes_through_its_own_node(self):
        self.use_proxycheck()
        self.once()
        self.age("ips.proxycheck", (1,), 8000)
        self.once()
        self.assertEqual(len(self.intelligence.proxycheck_calls), 2)
        self.choose("OpenAI", "🌐 本机·本地直连")
        self.once()
        self.choose("OpenAI", "ALL·优选")
        self.once()
        self.assertNotEqual(self.current("ALL"), REJECT)
        self.assertEqual(len(self.intelligence.proxycheck_calls), 3)
        self.assertTrue(
            all(
                source == address and not key
                for source, address, key in self.intelligence.proxycheck_calls
            )
        )

    def test_provider_change_keeps_cache_sources_separate_and_rechecks(self):
        self.once()
        old_reports = (self.state / "ips").read_bytes()
        self.intelligence.proxycheck_overrides["198.51.100.10"] = {
            "attack_history": {"vulnerability_probing": 1}
        }
        self.use_proxycheck()
        self.once()
        self.assertEqual((self.state / "ips").read_bytes(), old_reports)
        self.assertEqual(len(self.intelligence.lookups), 2)
        self.assertEqual(len(self.intelligence.proxycheck_calls), 2)
        self.assertEqual(self.current("SG"), REJECT)
        self.assertEqual(self.current("HK"), self.names[2])
        self.assertIn("198.51.100.10", (self.state / "ips.proxycheck").read_text())

    def test_legacy_ipqs_settings_and_eight_field_nodes_remain_compatible(self):
        del self.settings["reputation_provider"]
        self.save_settings()
        self.once()
        old_nodes = (
            "\n".join(
                "\t".join(line.split("\t")[:8])
                for line in (self.state / "nodes").read_text().splitlines()
            )
            + "\n"
        )
        write(self.state / "nodes", old_nodes)
        self.once()
        self.assertEqual(len(self.intelligence.lookups), 2)
        self.assertEqual(self.intelligence.proxycheck_calls, [])
        self.assertIn(self.current("SG"), self.names[:2])

    def test_proxycheck_ipv6_risk_and_global_budget_are_enforced(self):
        self.use_proxycheck()
        self.settings["check_ipv6"] = True
        self.save_settings()
        self.intelligence.proxycheck_overrides["2001:db8:0:0:0:0:0:10"] = {
            "attack_history": {"scan": 2}
        }
        self.once()
        self.assertEqual(self.current("SG"), REJECT)
        self.assertEqual(self.current("HK"), self.names[2])
        self.assertEqual(len(self.intelligence.proxycheck_calls), 4)
        self.assertTrue(
            all(
                source != "management" and not key
                for source, _, key in self.intelligence.proxycheck_calls
            )
        )
        self.settings["daily_budget"] = 4
        self.save_settings()
        self.age("nodes", (1, 6), 4000)
        self.age("ips.proxycheck", (1,), 90000)
        self.once()
        self.assertEqual(len(self.intelligence.proxycheck_calls), 4)
        self.assertEqual((self.state / "quota").read_text().split()[1], "4")

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
        registry = self.api("/providers/proxies")
        del registry["providers"]["1.主要地址"]["proxies"]
        controller = self.serve(
            http.server.ThreadingHTTPServer,
            SnapshotControllerHandler,
            upstream=f"http://127.0.0.1:{self.api_port}",
            calls=[],
            response_status=200,
            response_body=json.dumps(registry).encode(),
        )
        self.settings["controller"] = f"http://127.0.0.1:{controller.server_address[1]}"
        self.save_settings()
        self.once(expected_code=1)
        self.assertEqual({code: self.current(code) for code in previous}, previous)
        self.assertEqual(len(self.intelligence.lookups), 2)
        self.assertFalse(any(method == "PUT" for method, _ in controller.calls))
        self.assertIn("invalid snapshot", (self.state / "summary").read_text())
        controller.response_status = 503
        self.once(expected_code=1)
        self.assertEqual({code: self.current(code) for code in previous}, previous)
        self.assertEqual(len(self.intelligence.lookups), 2)
        self.assertIn("response unavailable", (self.state / "summary").read_text())

    def test_provider_renames_ignore_legacy_lists_and_preserve_settings(self):
        self.settings["providers"] = ["an old custom name", "missing-provider"]
        self.save_settings()
        personal = (self.root / "clash/private/preferred.json").read_bytes()
        self.once()
        previous = {code: self.current(code) for code in ("ALL", "SG", "HK")}
        names = {
            "1.主要地址": '订阅 "A" / 東京 ?',
            "2.备用地址": "second custom source",
            "3.额外地址": "以后还会改",
            "家宽账号": "private source renamed too",
        }
        self.rename_providers(names)
        self.once()
        self.assertEqual({code: self.current(code) for code in previous}, previous)
        self.assertEqual(len(self.intelligence.lookups), 2)
        self.assertEqual(
            (self.root / "clash/private/preferred.json").read_bytes(), personal
        )
        discovered = (self.state / "providers").read_text().splitlines()
        self.assertCountEqual(discovered, [ENCODE(name) for name in names.values()])
        self.assertIn(
            "Provider discovery: automatic", (self.state / "summary").read_text()
        )

    def test_added_and_deleted_subscription_is_seen_without_settings_changes(self):
        hong_kong = self.cfg["proxy-providers"]["1.主要地址"]["payload"].pop()
        self.reload_config()
        self.once()
        self.assertEqual(self.current("HK"), REJECT)
        self.assertEqual(len(self.intelligence.lookups), 1)
        personal = (self.root / "clash/private/preferred.json").read_bytes()

        self.cfg["proxy-providers"]["new subscription / 香港"] = {
            "type": "inline",
            "payload": [hong_kong],
        }
        self.reload_config()
        self.once()
        self.assertEqual(self.current("HK"), self.names[2])
        self.assertEqual(len(self.intelligence.lookups), 2)

        del self.cfg["proxy-providers"]["new subscription / 香港"]
        self.reload_config()
        self.once()
        self.assertEqual(self.current("HK"), REJECT)
        self.assertEqual(len(self.intelligence.lookups), 2)
        self.assertIn("198.51.100.20", (self.state / "ips").read_text())
        self.assertEqual(
            (self.root / "clash/private/preferred.json").read_bytes(), personal
        )

    def test_renamed_private_provider_is_excluded_by_landing_group_membership(self):
        self.cfg["proxy-providers"]["家宽账号"]["payload"] = [
            {
                "name": "residential-only-node",
                "type": "socks5",
                "server": "127.0.0.1",
                "port": self.nodes[2].server_address[1],
                "udp": False,
            }
        ]
        self.rename_providers({"家宽账号": "my private file / custom name"})
        self.once()
        self.assertNotIn(
            "residential-only-node", (self.state / "report.tsv").read_text()
        )
        self.assertIn("Candidate nodes: 3", (self.state / "summary").read_text())
        self.assertEqual(sum(path == "/ip" for path in self.nodes[2].paths), 1)

    def test_scope_filter_only_ranks_nodes_that_group_can_select(self):
        group = next(
            group
            for group in self.cfg["proxy-groups"]
            if group["name"] == "优选·SG出口"
        )
        group["filter"] = "^B "
        self.reload_config()
        self.once()
        self.assertEqual(self.current("SG"), self.names[1])
        self.assertEqual(self.current("HK"), self.names[2])

    def test_status_distinguishes_disabled_missing_key_and_empty_candidates(self):
        self.settings["enabled"] = False
        self.save_settings()
        self.once()
        self.assertIn(
            "Disabled: set enabled=true", (self.state / "summary").read_text()
        )
        self.settings.update(
            {"enabled": True, "reputation_provider": "ipqs", "api_key": ""}
        )
        self.save_settings()
        self.once()
        self.assertIn("IPQS API key missing", (self.state / "summary").read_text())
        self.use_proxycheck()
        self.cfg["proxy-providers"]["1.主要地址"]["payload"] = [
            {"name": "no-nodes", "type": "reject"}
        ]
        self.reload_config()
        self.once()
        self.assertIn("No candidate nodes", (self.state / "summary").read_text())
        self.assertEqual(self.intelligence.lookups, [])
        self.assertEqual(self.intelligence.proxycheck_calls, [])

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

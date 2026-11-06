"""AI route checks with real mihomo, repository rules and loopback-only services.

python tests/test_ai.py --mihomo /path/to/mihomo
No AI accounts, subscriptions, external DNS or public network destinations are used.
"""

import argparse
import json
import re
import shutil
import time
import unittest
from pathlib import Path

import test_landing as landing
import yaml

REPO = Path(__file__).resolve().parents[1]
SOURCE = yaml.safe_load((REPO / "box_bll/clash/config.yaml").read_bytes())
CASES = json.loads(
    (REPO / "tests/fixtures/ai-routing.json").read_text(encoding="utf-8")
)
AI_GROUPS = set(CASES["services"])
AI_PROVIDERS = {
    name: item
    for name, item in SOURCE["rule-providers"].items()
    if item["path"].startswith("./rules/AI-")
}
ALL_HOSTS = {
    host
    for kind in ("services", "ordinary")
    for hosts in CASES[kind].values()
    for host in hosts
} | set(CASES["shared"])


class RuleContractTests(unittest.TestCase):
    def test_local_rules_are_scoped_and_wired_before_parent_services(self):
        self.assertEqual(len(AI_PROVIDERS), 10)
        self.assertEqual(len(AI_GROUPS), 10)
        groups = {group["name"]: group for group in SOURCE["proxy-groups"]}
        rules = SOURCE["rules"]
        parent_indexes = [
            rules.index(rule)
            for rule in (
                "RULE-SET,Google_域,Google",
                "RULE-SET,Google_IP,Google,no-resolve",
                "RULE-SET,Microsoft_域,Microsoft",
                "RULE-SET,GitHub_域,GitHub",
                "RULE-SET,Twitter_域,Twitter(X)",
            )
        ]
        forbidden = {
            "google.com",
            "googleapis.com",
            "googleusercontent.com",
            "gstatic.com",
            "github.com",
            "githubusercontent.com",
            "microsoft.com",
            "bing.com",
            "x.com",
            "twimg.com",
            "amazonaws.com",
            "cloudinary.com",
            "cloudflare.com",
            "livekit.cloud",
            "auth0.com",
            "blob.core.windows.net",
            "azureedge.net",
            "azurefd.net",
            "storage.googleapis.com",
            "apis.google.com",
        }
        seen = set()
        for name, provider in AI_PROVIDERS.items():
            self.assertEqual(
                (provider["type"], provider["behavior"], provider["format"]),
                ("file", "classical", "text"),
            )
            self.assertNotIn("url", provider)
            refs = [r for r in rules if r.startswith(f"RULE-SET,{name},")]
            self.assertEqual(len(refs), 1)
            group = refs[0].split(",")[2]
            self.assertIn(group, AI_GROUPS)
            self.assertLess(rules.index(refs[0]), min(parent_indexes))
            self.assertGreater(
                rules.index(refs[0]), rules.index("RULE-SET,No-ads-all_域,广告拦截")
            )
            data = (REPO / "box_bll/clash" / provider["path"]).read_bytes()
            self.assertNotIn(b"\r", data)
            self.assertRegex(data.decode(), r"Reviewed: \d{4}-\d{2}-\d{2}")
            entries = [
                line.strip()
                for line in data.decode().splitlines()
                if line and not line.startswith("#")
            ]
            self.assertTrue(entries)
            for entry in entries:
                kind, domain = entry.split(",")
                self.assertIn(kind, ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-REGEX"))
                if kind == "DOMAIN-REGEX":
                    self.assertTrue(domain.startswith("^") and domain.endswith("$"))
                    matches = [
                        host
                        for host in CASES["services"][group]
                        if re.fullmatch(domain, host)
                    ]
                else:
                    self.assertRegex(domain, r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$")
                    matches = [
                        host
                        for host in CASES["services"][group]
                        if host == domain
                        or (kind == "DOMAIN-SUFFIX" and host.endswith("." + domain))
                    ]
                self.assertTrue(matches, f"No runtime fixture covers {name}: {entry}")
                self.assertNotIn(domain, forbidden)
                self.assertNotIn(entry, seen, entry)
                seen.add(entry)
        local_files = {
            path.name for path in (REPO / "box_bll/clash/rules").glob("AI-*.list")
        }
        self.assertEqual(
            local_files, {Path(p["path"]).name for p in AI_PROVIDERS.values()}
        )
        installer = (REPO / "customize.sh").read_text(encoding="utf-8")
        names = re.search(r'^AI_RULE_NAMES="([^"]+)"$', installer, re.MULTILINE)
        self.assertIsNotNone(names)
        self.assertEqual(local_files, {f"AI-{name}.list" for name in names[1].split()})
        for name in AI_GROUPS:
            proxies = groups[name]["proxies"]
            self.assertEqual(proxies[0], "总模式")
            self.assertIn("家宽落地", proxies)
            self.assertTrue(AI_GROUPS.isdisjoint(proxies))


class AIRoutingTests(unittest.TestCase):
    def setUp(self):
        if not landing.MIHOMO:
            self.skipTest("pass --mihomo for runtime routing tests")
        self.runtime = landing.RuntimeTests()
        self.addCleanup(self.runtime.doCleanups)
        self.runtime.setUp()
        run = self.runtime
        # Keep production ordering and bundled rule data. HTTP providers become
        # file providers so no external refresh or first download can occur.
        for name, original in SOURCE["rule-providers"].items():
            relative = original["path"]
            source = REPO / "box_bll/clash" / relative
            target = run.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            run.cfg["rule-providers"][name] = {
                "type": "file",
                "path": relative,
                "behavior": original["behavior"],
                "format": original["format"],
            }
        run.cfg["hosts"] = {host: "127.0.0.1" for host in ALL_HOSTS}
        for endpoint in (run.front_a, run.front_b, run.landing):
            endpoint.hosts = {host: "127.0.0.1" for host in ALL_HOSTS}

    def start(self, residential=False):
        run = self.runtime
        run.start(select_routes=False)
        run.choose("总模式", "🌐 本机·本地直连")
        if residential:
            run.choose("落地前置", "前置0")
            for group in AI_GROUPS:
                run.choose(group, "家宽落地")

    def request(self, host):
        run = self.runtime
        sock, _, _ = landing.connect_socks(run.mixed, host, run.web.server_address[1])
        with sock:
            source_port = str(sock.getsockname()[1])
            connection = None
            for _ in range(20):
                connection = next(
                    (
                        item
                        for item in (run.api("/connections")["connections"] or [])
                        if str(item["metadata"]["sourcePort"]) == source_port
                    ),
                    None,
                )
                if connection:
                    break
                time.sleep(0.05)
            self.assertIsNotNone(connection, host)
            sock.sendall(f"GET / HTTP/1.0\r\nHost: {host}\r\n\r\n".encode())
            data = b""
            while chunk := sock.recv(4096):
                data += chunk
            self.assertIn(b"fixture-ok", data)
            return connection

    def test_service_domains_use_their_group_and_residential_chain(self):
        self.start()
        # Inspect the business group before rematch: rematch replaces the public
        # connection chain with its sub-rule's final exit, hiding the outer group.
        for group, hosts in CASES["services"].items():
            for host in hosts:
                with self.subTest(group=group, host=host):
                    result = self.request(host)
                    self.assertIn(group, result["chains"])
                    self.assertIn("总模式", result["chains"])
        self.assertEqual(self.runtime.landing.requests, [])
        self.runtime.choose("落地前置", "前置0")
        for group, hosts in CASES["services"].items():
            self.runtime.choose(group, "家宽落地")
            for host in hosts:
                with self.subTest(residential_group=group, host=host):
                    before = len(self.runtime.landing.requests)
                    result = self.request(host)
                    self.assertIn("家宽·出口", result["chains"])
                    self.assertEqual(len(self.runtime.landing.requests), before + 1)
        self.assertTrue(self.runtime.front_a.requests)
        self.assertTrue(all(self.runtime.landing.auth_attempts))

    def test_google_and_other_ordinary_traffic_do_not_use_residential_exit(self):
        self.start(residential=True)
        for group, hosts in CASES["ordinary"].items():
            for host in hosts:
                with self.subTest(group=group, host=host):
                    before = len(self.runtime.landing.requests)
                    result = self.request(host)
                    self.assertIn(group, result["chains"])
                    self.assertTrue(AI_GROUPS.isdisjoint(result["chains"]))
                    self.assertNotIn("家宽·出口", result["chains"])
                    self.assertEqual(len(self.runtime.landing.requests), before)
        for host in CASES["shared"]:
            with self.subTest(shared=host):
                before = len(self.runtime.landing.requests)
                result = self.request(host)
                self.assertTrue(AI_GROUPS.isdisjoint(result["chains"]))
                self.assertNotIn("家宽·出口", result["chains"])
                self.assertEqual(len(self.runtime.landing.requests), before)

    def test_defaults_and_independent_service_selection(self):
        self.start()
        run = self.runtime
        groups = run.api("/proxies")["proxies"]
        for group in AI_GROUPS:
            self.assertEqual(groups[group]["now"], "总模式")
        self.assertNotIn("家宽·出口", self.request("gemini.google.com")["chains"])
        run.choose("落地前置", "前置0")
        run.choose("Gemini", "家宽落地")
        run.choose("OpenAI", "家宽落地")
        self.assertIn("家宽·出口", self.request("gemini.google.com")["chains"])
        self.assertNotIn("家宽·出口", self.request("notebooklm.google.com")["chains"])
        self.assertIn("家宽·出口", self.request("api.openai.com")["chains"])
        run.choose("Gemini", "总模式")
        groups = run.api("/proxies")["proxies"]
        self.assertEqual(groups["Gemini"]["now"], "总模式")
        self.assertEqual(groups["OpenAI"]["now"], "家宽落地")
        self.assertEqual(groups["NotebookLM"]["now"], "总模式")
        self.assertNotIn("家宽·出口", self.request("notebooklm.google.com")["chains"])
        self.assertNotIn("家宽·出口", self.request("gemini.google.com")["chains"])
        self.assertIn("家宽·出口", self.request("api.openai.com")["chains"])

    def test_residential_failure_does_not_fall_through_to_google(self):
        self.runtime.set_account("wrong-password")
        self.start(residential=True)
        run = self.runtime
        self.assertFalse(run.fetch("gemini.google.com"))
        self.assertIn(False, run.landing.auth_attempts)
        self.assertNotIn("家宽·出口", self.request("www.google.com")["chains"])

    def test_udp_is_rejected_only_for_service_using_residential_exit(self):
        self.start(residential=True)
        run = self.runtime
        self.assertFalse(run.udp_request("gemini.google.com"))
        self.assertEqual(run.udp.requests, [])
        self.assertEqual(run.landing.requests, [])
        run.choose("Gemini", "总模式")
        self.assertTrue(run.udp_request("gemini.google.com"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mihomo")
    args, rest = parser.parse_known_args()
    landing.MIHOMO = str(Path(args.mihomo).resolve()) if args.mihomo else None
    unittest.main(argv=[__file__, *rest], verbosity=2)

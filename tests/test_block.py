"""Run the real block-list and lifecycle code against a temporary firewall.

No Android device, installed package or host firewall is accessed.
"""

import argparse
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHELL = None


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


class BlockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="surfing-block-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scripts = self.root / "scripts"
        self.bin = self.root / "bin"
        self.log = self.root / "firewall.log"
        self.list = self.root / "block.list"
        write(self.list, "sample.one\n")
        write(
            self.scripts / "box.config",
            f'box_path="{self.root.as_posix()}"\n',
        )
        source = (REPO / "box_bll/scripts/box.block").read_text(encoding="utf-8")
        source = source.replace("#!/system/bin/sh", "#!/bin/sh")
        source = source.replace("/data/adb/box_bll", self.root.as_posix())
        source = source.replace("/system/bin/", self.bin.as_posix() + "/")
        write(self.scripts / "box.block", source)
        write(
            self.bin / "pm",
            "#!/bin/sh\nprintf 'package:sample.one uid:12345\\n"
            "package:sample.two uid:12346\\n'\n",
        )
        firewall = """#!/bin/sh
family=${0##*/}
state="$BLOCK_TEST_ROOT/$family"
printf '%s %s\n' "$family" "$*" >> "$BLOCK_TEST_ROOT/firewall.log"
case " $* " in
    *' -D OUTPUT -j SURF_BLOCK '*)
        [ -f "$state.link" ] || exit 1
        rm -f "$state.link" ;;
    *' -I OUTPUT 1 -j SURF_BLOCK '*) touch "$state.link" ;;
    *' -N SURF_BLOCK '*) touch "$state.chain" ;;
    *' -F SURF_BLOCK '*) : > "$state.rules" ;;
    *' -X SURF_BLOCK '*) rm -f "$state.chain" ;;
    *' -A SURF_BLOCK '*) printf '%s\n' "$*" >> "$state.rules" ;;
    *) exit 1 ;;
esac
"""
        for family in ("iptables", "ip6tables"):
            write(self.bin / family, firewall)
        self.env = dict(
            os.environ,
            BLOCK_TEST_ROOT=self.root.as_posix(),
            ASH_STANDALONE="0",
        )

    def run_script(self, path, *args):
        result = subprocess.run(
            [SHELL, path.as_posix(), *args],
            env=self.env,
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            (result.stdout + result.stderr).decode(errors="replace"),
        )
        return result

    def block(self, *args):
        return self.run_script(self.scripts / "box.block", *args)

    def assert_firewall(self, enabled):
        for family in ("iptables", "ip6tables"):
            self.assertEqual((self.root / f"{family}.link").exists(), enabled)
            self.assertEqual((self.root / f"{family}.chain").exists(), enabled)
            rules = (self.root / f"{family}.rules").read_text()
            self.assertEqual("--uid-owner 12345" in rules, enabled)

    def test_delete_last_entry_removes_both_firewalls(self):
        self.block("enable")
        self.assert_firewall(True)
        self.block("del", "sample.one")
        self.assertEqual(self.list.read_text(), "")
        self.assert_firewall(False)
        self.block("del", "sample.one")
        self.assert_firewall(False)
        self.assertEqual(list(self.root.glob("block.list.*")), [])

    def test_delete_preserves_other_entries_and_comments(self):
        write(self.list, "# personal list\nsample.one\nsample.two\n")
        self.block("del", "sample.two")
        self.assertEqual(self.list.read_text(), "# personal list\nsample.one\n")
        self.assert_firewall(True)
        self.block("del", "sample.missing")
        self.assertEqual(self.list.read_text(), "# personal list\nsample.one\n")

    def service_harness(self, commands):
        source = (REPO / "box_bll/scripts/box.service").read_text(encoding="utf-8")
        functions = "\n".join(
            re.search(rf"(?ms)^{name}\(\) \{{.*?^\}}", source)[0]
            for name in ("start_service", "stop_service")
        )
        path = self.root / "service-test.sh"
        write(
            path,
            f'scripts_dir="{self.scripts.as_posix()}"\n'
            f'pid_file="{self.root.as_posix()}/core.pid"\n'
            "log() { :; }\ncheck_permission() { return 0; }\n"
            'clear_port_blockers() { :; }\nstart_bin() { echo 1 > "$pid_file"; }\n'
            "display_bin_status() { return 1; }\n" + functions + "\n" + commands,
        )
        self.run_script(path)

    def test_core_stop_cleans_even_when_core_is_already_absent(self):
        self.block("enable")
        self.service_harness("stop_service\n")
        self.assert_firewall(False)

    def test_core_restart_reapplies_rules(self):
        self.block("enable")
        self.service_harness("stop_service\nstart_service\n")
        self.assert_firewall(True)

    def test_module_disable_cleans_both_families(self):
        self.block("enable")
        source = (REPO / "box_bll/scripts/box.iptables").read_text(encoding="utf-8")
        branch = source.split("\n  disable)\n", 1)[1].split("\n    ;;", 1)[0]
        path = self.root / "disable-test.sh"
        write(
            path,
            f'scripts_dir="{self.scripts.as_posix()}"\n'
            f'ipv6_disabled_flag="{self.root.as_posix()}/absent"\n'
            "log() { :; }\npgrep() { return 1; }\nxargs() { :; }\n"
            "destroy_all_rules() { :; }\nsleep() { :; }\n"
            "disable_module() {\n" + branch + "\n}\ndisable_module\n",
        )
        self.run_script(path)
        self.assert_firewall(False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shell", required=True)
    args, remaining = parser.parse_known_args()
    SHELL = args.shell
    unittest.main(argv=[__file__, *remaining], verbosity=2)

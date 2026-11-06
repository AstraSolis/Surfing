"""Offline release-chain tests; all downloads and GitHub writes use local fixtures."""

import copy
import gzip
import io
import json
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import publish_release as publish
from tools import release

REPO = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
EPOCH = 1700000000
ELF = b"\x7fELF\x02\x01" + b"\0" * 12 + b"\xb7\x00" + b"BusyBox v1.36.1-fixture\0"


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


class FakeGitHub:
    def __init__(self, info):
        self.info = info
        self.releases = {}
        self.contents = {}
        self.events = []
        self.latest = None
        self.fail_after = None
        self.commit = COMMIT

    def tag_commit(self, tag):
        return self.commit

    def get_release(self, tag):
        return copy.deepcopy(self.releases.get(tag))

    def all_releases(self):
        return copy.deepcopy(list(self.releases.values()))

    def add_asset(self, item, name, data):
        identifier = len(self.contents) + 1
        asset = {
            "id": identifier,
            "name": name,
            "size": len(data),
            "digest": "sha256:" + release.sha256(data),
        }
        self.contents[identifier] = data
        item["assets"].append(asset)

    def previous(self, code, prerelease=False, missing_manifest=False):
        tag = f"previous-{code}"
        item = {
            "id": 99,
            "tag_name": tag,
            "draft": False,
            "prerelease": prerelease,
            "assets": [],
        }
        if not missing_manifest:
            self.add_asset(item, "Surfing.json", release.encoded({"versionCode": code}))
        self.releases[tag] = item
        if not prerelease:
            self.latest = tag

    def read_asset(self, asset):
        return self.contents[asset["id"]]

    def create_draft(self, info, directory):
        self.events.append("draft")
        item = {
            "id": 1,
            "tag_name": info["tag"],
            "draft": True,
            "prerelease": False,
            "assets": [],
        }
        self.releases[info["tag"]] = item
        return copy.deepcopy(item)

    def upload(self, tag, path):
        item = self.releases[tag]
        if self.fail_after is not None and len(item["assets"]) == self.fail_after:
            raise release.ReleaseError("Simulated interrupted upload")
        self.events.append("upload:" + path.name)
        self.add_asset(item, path.name, path.read_bytes())

    def publish(self, item):
        self.events.append("publish")
        stored = self.releases[item["tag_name"]]
        stored["draft"] = False
        self.latest = stored["tag_name"]
        return copy.deepcopy(stored)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="surfing-release-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / "source"
        self.cache = self.directory / "cache"
        self.output = self.directory / "stable"
        self.root.mkdir()
        self.cache.mkdir()
        for name in release.REQUIRED - {"build-info.json", "SurfingTile.zip"}:
            write(self.root / name, "fixture\n")
        write(self.root / "module.prop", (REPO / "module.prop").read_bytes())
        self.prop = release.version_settings(self.root)
        write(
            self.root / "changelog.md",
            f"# {self.prop['version']}\n\n- Fixture changes.\n\n# v7.8.4\n\n- Upstream.\n",
        )
        write(
            self.root / "Surfing.json",
            release.encoded(release.update_manifest(release.metadata(self.prop))),
        )
        write(self.root / "box_bll/bin/busybox", ELF)
        lock = release.dependencies(REPO)
        blobs = {
            "mihomo": gzip.compress(ELF, mtime=0),
            "curl": ELF,
            "zashboard": release.zip_bytes(
                {"dist/index.html": b"<html>fixture</html>"}, EPOCH
            ),
        }
        for name, blob in blobs.items():
            lock[name]["sha256"] = release.sha256(blob)
            write(self.cache / lock[name]["sha256"], blob)
        write(self.root / "release/dependencies.json", release.encoded(lock))
        apk = release.zip_bytes({"AndroidManifest.xml": b"fixture"}, EPOCH)
        tile = self.root / "app/version/com.github.surfing"
        write(tile / "SurfingTile_7.0.0_release.apk", apk)
        write(
            tile / "release.json",
            release.encoded(
                [
                    {
                        "versionName": "v7.0.0",
                        "versionCode": 26101301,
                        "fileSize": len(apk),
                        "sha256": release.sha256(apk),
                    }
                ]
            ),
        )
        self.inventory()

    def inventory(self, dirty=False):
        files = {
            path.relative_to(self.root).as_posix(): release.file_hash(path)
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
            and path.name != release.SNAPSHOT
            and not release.private_name(path.relative_to(self.root).as_posix())
        }
        write(
            self.root / release.SNAPSHOT,
            release.encoded(
                {"commit": COMMIT, "epoch": EPOCH, "dirty": dirty, "files": files}
            ),
        )

    def build(self, channel="stable", output=None):
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("Tests must stay offline"),
            ),
            redirect_stdout(io.StringIO()),
        ):
            return release.build(self.root, channel, output or self.output, self.cache)

    def sums(self):
        write(
            self.output / "SHA256SUMS",
            "".join(
                f"{release.file_hash(path)}  {path.name}\n"
                for path in sorted(self.output.iterdir())
                if path.name != "SHA256SUMS"
            ),
        )

    def test_stable_manifest_and_packaged_identity_agree(self):
        info = self.build()
        manifest = release.read_json(self.output / "Surfing.json")
        self.assertEqual(manifest["version"], info["version"])
        self.assertEqual(manifest["versionCode"], int(self.prop["versionCode"]))
        self.assertIn(f"/download/{info['tag']}/{info['zipName']}", manifest["zipUrl"])
        self.assertEqual(
            manifest["changelog"],
            f"{release.RELEASE_URL}/download/{info['tag']}/changelog.md",
        )
        self.assertNotIn("latest", manifest["zipUrl"])
        self.assertEqual(
            (self.root / "module.prop").read_bytes(),
            (REPO / "module.prop").read_bytes(),
        )
        release.verify(self.output, self.root)

    def test_alpha_is_manual_and_stable_can_replace_it(self):
        info = self.build("alpha", self.directory / "alpha")
        self.assertIsNone(info["tag"])
        self.assertLess(info["versionCode"], int(self.prop["versionCode"]))
        self.assertFalse((self.directory / "alpha/Surfing.json").exists())
        with zipfile.ZipFile(self.directory / "alpha" / info["zipName"]) as archive:
            prop = release.properties(archive.read("module.prop").decode())
            self.assertEqual(prop["updateJson"], release.UPDATE_URL)

    def test_stale_preview_wrong_tag_and_invalid_code_fail(self):
        with self.assertRaises(release.ReleaseError):
            release.check(self.root, "v7.8.4")
        write(self.root / "Surfing.json", "{}")
        with self.assertRaisesRegex(release.ReleaseError, "stale"):
            release.check(self.root)
        write(
            self.root / "module.prop",
            (self.root / "module.prop")
            .read_text(encoding="utf-8")
            .replace(f"versionCode={self.prop['versionCode']}", "versionCode=1653"),
        )
        with self.assertRaises(release.ReleaseError):
            release.version_settings(self.root)

    def test_fresh_zip_removes_private_and_old_entries(self):
        write(
            self.root / "box_bll/clash/private/landing.yaml",
            "password: TEST-ONLY-SECRET\n",
        )
        write(self.root / ".idea/workspace.xml", "not for devices")
        write(self.root / "tests/output.txt", "not for devices")
        self.inventory()
        name = release.metadata(self.prop)["zipName"]
        self.output.mkdir()
        write(
            self.output / name,
            release.zip_bytes(
                {
                    "box_bll/clash/private/landing.yaml": b"TEST-ONLY-SECRET",
                    "Surfing_previous.zip": b"stale",
                    "tests/output.txt": b"stale",
                },
                EPOCH,
            ),
        )
        info = self.build()
        with zipfile.ZipFile(self.output / name) as archive:
            self.assertNotIn("box_bll/clash/private/landing.yaml", archive.namelist())
            self.assertNotIn("Surfing_previous.zip", archive.namelist())
            self.assertNotIn("tests/output.txt", archive.namelist())
            self.assertNotIn(".idea/workspace.xml", archive.namelist())
        self.assertNotIn(b"TEST-ONLY-SECRET", release.encoded(info))

    def test_ai_rules_and_usage_guide_are_packaged(self):
        self.assertEqual(
            release.AI_RULE_FILES,
            {
                path.relative_to(REPO).as_posix()
                for path in (REPO / "box_bll/clash/rules").glob("AI-*.list")
            },
        )
        for name in release.AI_RULE_FILES | {"docs/AI-ROUTING.md"}:
            write(self.root / name, (REPO / name).read_bytes())
        self.inventory()
        info = self.build()
        with zipfile.ZipFile(self.output / info["zipName"]) as archive:
            for name in release.AI_RULE_FILES | {"docs/AI-ROUTING.md"}:
                self.assertEqual(archive.read(name), (REPO / name).read_bytes())

    def test_missing_ai_rules_are_rejected(self):
        (self.root / "box_bll/clash/rules/AI-Gemini.list").unlink()
        self.inventory()
        with self.assertRaisesRegex(release.ReleaseError, "missing required files"):
            self.build()

    def test_same_source_build_is_repeatable(self):
        self.build()
        hashes = {path.name: release.file_hash(path) for path in self.output.iterdir()}
        self.build()
        self.assertEqual(
            hashes,
            {path.name: release.file_hash(path) for path in self.output.iterdir()},
        )

    def test_dependency_corruption_fails_before_output(self):
        item = release.dependencies(self.root)["mihomo"]
        write(self.cache / item["sha256"], b"corrupted download")
        with self.assertRaisesRegex(release.ReleaseError, "checksum"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_apk_must_match_manifest(self):
        write(
            self.root / "app/version/com.github.surfing/SurfingTile_7.0.0_release.apk",
            b"wrong APK",
        )
        self.inventory()
        with self.assertRaisesRegex(release.ReleaseError, "APK differs"):
            self.build()

    def test_changed_snapshot_requires_reexport(self):
        write(self.root / "customize.sh", "changed after snapshot\n")
        with self.assertRaisesRegex(release.ReleaseError, "snapshot changed"):
            self.build()

    def test_snapshot_excludes_private_files(self):
        write(self.root / "box_bll/clash/private/landing.yaml", "TEST-ONLY-SECRET")
        destination = self.directory / "snapshot"
        release.snapshot(self.root, destination)
        self.assertFalse((destination / "box_bll/clash/private").exists())
        self.assertEqual(
            release.source_record(self.root), release.source_record(destination)
        )

    def test_unsafe_zashboard_archive_is_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("dist/../../private/landing.yaml", "TEST-ONLY-SECRET")
        with self.assertRaises(release.ReleaseError):
            release.zashboard_files(stream.getvalue())

    def test_changed_download_url_is_rejected_even_with_new_checksums(self):
        self.build()
        manifest = release.read_json(self.output / "Surfing.json")
        manifest["zipUrl"] = (
            "https://github.com/GitMetaio/Surfing/releases/latest/download/wrong.zip"
        )
        write(self.output / "Surfing.json", release.encoded(manifest))
        self.sums()
        with self.assertRaisesRegex(release.ReleaseError, "manifest does not match"):
            release.verify(self.output)

    def test_modified_zip_and_missing_assets_are_rejected(self):
        info = self.build()
        with (self.output / info["zipName"]).open("ab") as handle:
            handle.write(b"changed")
        with self.assertRaisesRegex(release.ReleaseError, "SHA-256 mismatch"):
            release.verify(self.output)
        (self.output / "changelog.md").unlink()
        with self.assertRaisesRegex(release.ReleaseError, "missing release assets"):
            release.verify(self.output)

    def test_private_entry_rejected_even_with_recalculated_outer_checksums(self):
        info = self.build()
        with zipfile.ZipFile(self.output / info["zipName"], "a") as archive:
            archive.writestr("box_bll/clash/private/landing.yaml", "TEST-ONLY-SECRET")
        self.sums()
        with self.assertRaisesRegex(release.ReleaseError, "Forbidden"):
            release.verify(self.output)

    def test_first_release_becomes_visible_only_after_all_uploads(self):
        info = self.build()
        api = FakeGitHub(info)
        api.previous(999999, prerelease=True)
        publish.publish_bundle(self.output, info, api)
        self.assertEqual(api.events[0], "draft")
        self.assertEqual(api.events[-1], "publish")
        self.assertEqual(len([e for e in api.events if e.startswith("upload:")]), 5)
        self.assertEqual(api.latest, info["tag"])

    def test_failed_upload_keeps_latest_and_can_resume_without_overwrites(self):
        info = self.build()
        api = FakeGitHub(info)
        api.previous(info["versionCode"] - 1)
        previous = api.latest
        api.fail_after = 2
        with self.assertRaisesRegex(release.ReleaseError, "interrupted"):
            publish.publish_bundle(self.output, info, api)
        self.assertEqual(api.latest, previous)
        self.assertTrue(api.get_release(info["tag"])["draft"])
        self.assertNotIn("publish", api.events)
        api.fail_after = None
        publish.publish_bundle(self.output, info, api)
        uploads = [e for e in api.events if e.startswith("upload:")]
        self.assertEqual(len(uploads), len(set(uploads)))
        self.assertEqual(api.latest, info["tag"])

    def test_repeat_public_release_never_moves_latest_back(self):
        info = self.build()
        api = FakeGitHub(info)
        publish.publish_bundle(self.output, info, api)
        api.previous(info["versionCode"] + 1)
        latest, before = api.latest, list(api.events)
        publish.publish_bundle(self.output, info, api)
        self.assertEqual(api.events, before)
        self.assertEqual(api.latest, latest)

    def test_nonincreasing_version_is_blocked_before_draft_creation(self):
        info = self.build()
        for code in (info["versionCode"], info["versionCode"] + 1):
            with self.subTest(code=code):
                api = FakeGitHub(info)
                api.previous(code)
                with self.assertRaisesRegex(release.ReleaseError, "must increase"):
                    publish.publish_bundle(self.output, info, api)
                self.assertEqual(api.events, [])

    def test_unmanaged_stable_release_requires_inspection(self):
        info = self.build()
        api = FakeGitHub(info)
        api.previous(1653, missing_manifest=True)
        with self.assertRaisesRegex(release.ReleaseError, "unique Surfing.json"):
            publish.publish_bundle(self.output, info, api)
        self.assertEqual(api.events, [])

    def test_different_draft_asset_is_never_clobbered(self):
        info = self.build()
        api = FakeGitHub(info)
        api.create_draft(info, self.output)
        api.add_asset(api.releases[info["tag"]], "Surfing.json", b"different")
        with self.assertRaisesRegex(release.ReleaseError, "not be overwritten"):
            publish.publish_bundle(self.output, info, api)
        self.assertIsNone(api.latest)
        self.assertEqual(api.events, ["draft"])

    def test_remote_asset_hash_fallback_verifies_downloaded_bytes(self):
        info = self.build()
        api = FakeGitHub(info)
        publish.publish_bundle(self.output, info, api)
        for asset in api.releases[info["tag"]]["assets"]:
            asset.pop("digest")
        publish.publish_bundle(self.output, info, api)
        api.contents[1] = b"tampered"
        with self.assertRaises(release.ReleaseError):
            publish.publish_bundle(self.output, info, api)

    def test_dirty_or_wrong_source_cannot_publish(self):
        info = self.build()
        api = FakeGitHub(info)
        info["source"]["dirty"] = True
        with self.assertRaisesRegex(release.ReleaseError, "Uncommitted"):
            publish.publish_bundle(self.output, info, api)
        info["source"]["dirty"] = False
        api.commit = "b" * 40
        with self.assertRaisesRegex(release.ReleaseError, "source commit"):
            publish.publish_bundle(self.output, info, api)
        self.assertEqual(api.events, [])

    def test_alpha_cannot_publish_to_releases(self):
        info = self.build("alpha", self.directory / "alpha")
        with self.assertRaisesRegex(release.ReleaseError, "Actions artifacts"):
            publish.publish_bundle(self.directory / "alpha", info, FakeGitHub(info))

    def test_github_adapter_publishes_complete_draft_as_latest_stable(self):
        response = subprocess.CompletedProcess(
            [],
            0,
            stdout=release.encoded({"draft": False, "prerelease": False}),
            stderr=b"",
        )
        with patch("subprocess.run", return_value=response) as request:
            publish.GitHub().publish({"id": 123})
        args = request.call_args.args[0]
        self.assertIn("repos/AstraSolis/Surfing/releases/123", args)
        self.assertEqual(args[args.index("--method") + 1], "PATCH")
        self.assertEqual(
            json.loads(request.call_args.kwargs["input"]),
            {"draft": False, "prerelease": False, "make_latest": "true"},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

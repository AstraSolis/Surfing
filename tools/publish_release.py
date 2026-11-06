#!/usr/bin/env python3
"""Publish an already verified stable bundle. This command writes to GitHub."""

import argparse
import json
import os
import subprocess
from pathlib import Path

if __package__:
    from .release import (
        REPOSITORY,
        ROOT,
        ReleaseError,
        encoded,
        file_hash,
        require,
        sha256,
        verify,
    )
else:
    from release import (
        REPOSITORY,
        ROOT,
        ReleaseError,
        encoded,
        file_hash,
        require,
        sha256,
        verify,
    )


class GitHub:
    """Small gh adapter; tokens stay in gh's environment, never in command arguments."""

    prefix = f"repos/{REPOSITORY}"

    def command(self, args, data=None, missing_ok=False):
        result = subprocess.run(
            ["gh", *args], input=data, capture_output=True, check=False
        )
        if result.returncode:
            error = result.stderr.decode("utf-8", errors="replace")
            if missing_ok and "(HTTP 404)" in error:
                return None
            raise ReleaseError(f"GitHub operation failed: {error.strip()}")
        return result.stdout

    def api(self, endpoint, data=None, missing_ok=False):
        args = ["api", f"{self.prefix}/{endpoint}"]
        if data is not None:
            args.extend(["--method", "PATCH", "--input", "-"])
        result = self.command(
            args, encoded(data) if data is not None else None, missing_ok
        )
        return json.loads(result) if result is not None else None

    def get_release(self, tag):
        return self.api(f"releases/tags/{tag}", missing_ok=True)

    def all_releases(self):
        page = 1
        while True:
            items = self.api(f"releases?per_page=100&page={page}")
            require(isinstance(items, list), "Invalid releases API response")
            yield from items
            if len(items) < 100:
                break
            page += 1

    def tag_commit(self, tag):
        return self.api(f"commits/{tag}")["sha"]

    def read_asset(self, asset):
        return self.command(
            [
                "api",
                f"{self.prefix}/releases/assets/{asset['id']}",
                "-H",
                "Accept: application/octet-stream",
            ]
        )

    def create_draft(self, info, directory):
        self.command(
            [
                "release",
                "create",
                info["tag"],
                "--repo",
                REPOSITORY,
                "--verify-tag",
                "--draft",
                "--latest=false",
                "--title",
                f"Surfing AstraSolis {info['baseVersion']}",
                "--notes-file",
                str(directory / "changelog.md"),
            ]
        )
        return self.get_release(info["tag"])

    def upload(self, tag, path):
        # No --clobber: even a draft's existing assets must match before resuming.
        self.command(["release", "upload", tag, str(path), "--repo", REPOSITORY])

    def publish(self, item):
        return self.api(
            f"releases/{item['id']}",
            {
                "draft": False,
                "prerelease": False,
                "make_latest": "true",
            },
        )


def asset_matches(api, asset, path):
    digest = asset.get("digest")
    if not digest:
        digest = "sha256:" + sha256(api.read_asset(asset))
    return asset["size"] == path.stat().st_size and digest == "sha256:" + file_hash(
        path
    )


def check_assets(api, item, paths, complete):
    assets = {asset["name"]: asset for asset in item["assets"]}
    require(len(assets) == len(item["assets"]), "Duplicate remote asset names")
    require(
        set(assets) <= set(paths), "Release has unexpected assets; inspect it manually"
    )
    if complete:
        require(set(assets) == set(paths), "Release is missing assets")
    for name, asset in assets.items():
        require(
            asset_matches(api, asset, paths[name]),
            "Existing release asset differs; it will not be overwritten",
        )
    return assets


def check_version_increases(api, info):
    for item in api.all_releases():
        if item["draft"] or item["prerelease"]:
            continue
        assets = [asset for asset in item["assets"] if asset["name"] == "Surfing.json"]
        require(
            len(assets) == 1,
            "Existing stable release has no unique Surfing.json; inspect before publishing",
        )
        previous = json.loads(api.read_asset(assets[0]))
        require(
            type(previous.get("versionCode")) is int, "Invalid published versionCode"
        )
        require(
            info["versionCode"] > previous["versionCode"],
            "versionCode must increase beyond every published stable release",
        )


def publish_bundle(directory, info, api):
    require(
        info["channel"] == "stable", "Alpha is distributed only as Actions artifacts"
    )
    require(info["source"]["dirty"] is False, "Uncommitted builds cannot be published")
    tag = info["tag"]
    require(
        api.tag_commit(tag) == info["source"]["commit"],
        "Remote tag does not match the built source commit",
    )
    paths = {path.name: path for path in directory.iterdir()}
    current = api.get_release(tag)
    if current is not None:
        require(not current["prerelease"], "Stable tag already belongs to a prerelease")
        check_assets(api, current, paths, complete=not current["draft"])
        if not current["draft"]:
            # Rerunning an old release never moves latest back or changes public assets.
            return "Already published; all assets match. No changes made."
    check_version_increases(api, info)
    if current is None:
        current = api.create_draft(info, directory)
    require(current["draft"], "Expected an unpublished draft")
    existing = check_assets(api, current, paths, complete=False)
    for name, path in sorted(paths.items()):
        if name not in existing:
            api.upload(tag, path)
    current = api.get_release(tag)
    require(current["draft"], "Release changed while uploading; inspect it manually")
    check_assets(api, current, paths, complete=True)
    require(
        api.tag_commit(tag) == info["source"]["commit"], "Tag changed during upload"
    )
    check_version_increases(api, info)
    # The sole visibility change happens after every asset is present and verified.
    published = api.publish(current)
    require(
        not published["draft"] and not published["prerelease"],
        "Release did not become stable",
    )
    check_assets(api, published, paths, complete=True)
    return f"Published {tag}: https://github.com/{REPOSITORY}/releases/tag/{tag}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        require(
            os.environ.get("GITHUB_REPOSITORY", REPOSITORY) == REPOSITORY,
            "Unexpected workflow repository",
        )
        info = verify(args.directory, ROOT)
        print(publish_bundle(args.directory, info, GitHub()))
    except (ReleaseError, OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Publish error: {error}\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build and verify Surfing bundles. Python 3.10+, standard library only."""

import argparse
import gzip
import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "AstraSolis/Surfing"
RELEASE_URL = f"https://github.com/{REPOSITORY}/releases"
UPDATE_URL = f"{RELEASE_URL}/latest/download/Surfing.json"
SNAPSHOT = ".source-snapshot.json"
VERSION_RE = r"v[0-9]+\.[0-9]+\.[0-9]+-astra\.[1-9][0-9]*"
ROOT_PAYLOAD = {
    "module.prop",
    "customize.sh",
    "Surfing_service.sh",
    "uninstall.sh",
    "LICENSE",
    "README.md",
    "README_CN.md",
    "changelog.md",
    "docs/MIGRATION.md",
    "docs/AI-ROUTING.md",
    "docs/PREFERRED.md",
}
AI_RULE_FILES = {
    f"box_bll/clash/rules/AI-{name}.list"
    for name in (
        "OpenAI",
        "Gemini",
        "AIStudio",
        "NotebookLM",
        "Claude",
        "Perplexity",
        "Grok",
        "MicrosoftCopilot",
        "GitHubCopilot",
        "Other",
    )
}
REQUIRED = {
    "module.prop",
    "customize.sh",
    "Surfing_service.sh",
    "uninstall.sh",
    "LICENSE",
    "META-INF/com/google/android/update-binary",
    "META-INF/com/google/android/updater-script",
    "webroot/index.html",
    "box_bll/bin/busybox",
    "box_bll/bin/curl",
    "box_bll/bin/clash",
    "box_bll/scripts/box.landing",
    "box_bll/scripts/box.preferred",
    "box_bll/scripts/box.preferred.json.awk",
    "box_bll/scripts/box.preferred.policy.awk",
    "box_bll/scripts/box.config",
    "box_bll/scripts/box.service",
    "box_bll/scripts/box.iptables",
    "box_bll/clash/config.yaml",
    "box_bll/clash/landing.example.yaml",
    "box_bll/clash/preferred.example.json",
    "box_bll/clash/rules/LinuxDO.mrs",
    "docs/AI-ROUTING.md",
    "docs/PREFERRED.md",
    "box_bll/clash/webroot/Zash/index.html",
    "SurfingTile.zip",
    "build-info.json",
} | AI_RULE_FILES


class ReleaseError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def properties(text):
    result = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            require(key not in result, f"Duplicate module property: {key}")
            result[key] = value
    return result


def version_settings(root):
    prop = properties((root / "module.prop").read_text(encoding="utf-8"))
    require(prop.get("id") == "Surfing", "Module id must remain Surfing")
    require(
        prop.get("updateJson") == UPDATE_URL,
        "Module must follow the fork's stable release asset",
    )
    require(
        re.fullmatch(VERSION_RE, prop["version"]), "Expected version vX.Y.Z-astra.N"
    )
    require(prop["versionCode"].isdigit(), "versionCode must be an integer")
    require(
        1653 < int(prop["versionCode"]) <= 2147483647,
        "Stable versionCode must exceed 1653 and fit int32",
    )
    require(
        "GitMetaio" in prop["author"] and "AstraSolis" in prop["author"],
        "Keep upstream and fork attribution",
    )
    return prop


def metadata(prop, channel="stable", commit=None):
    require(channel in ("stable", "alpha"), "Unknown build channel")
    if commit is not None:
        require(
            re.fullmatch(r"[0-9a-f]{40}", commit), "A full source commit is required"
        )
    require(channel == "stable" or commit is not None, "Alpha requires a source commit")
    version = prop["version"]
    suffix = (
        f" ({'release' if channel == 'stable' else 'alpha'}-{commit[:7]})"
        if commit
        else ""
    )
    return {
        "baseVersion": version,
        "version": version + suffix,
        "versionCode": int(prop["versionCode"]) - (channel == "alpha"),
        "stableVersionCode": int(prop["versionCode"]),
        "channel": channel,
        "tag": version if channel == "stable" else None,
        "zipName": f"Surfing_{version}_release.zip"
        if channel == "stable"
        else f"Surfing_{version}_alpha_{commit[:12]}.zip",
    }


def update_manifest(meta):
    require(meta["channel"] == "stable", "Alpha has no module update manifest")
    base = f"{RELEASE_URL}/download/{meta['tag']}"
    return {
        "version": meta["version"],
        "versionCode": meta["versionCode"],
        "zipUrl": f"{base}/{meta['zipName']}",
        "changelog": f"{base}/changelog.md",
    }


def release_notes(root, version):
    text = (root / "changelog.md").read_text(encoding="utf-8")
    require(
        text.startswith(f"# {version}\n"),
        "First changelog heading must match module.prop",
    )
    return text.split("\n# ", 1)[0].rstrip() + "\n"


def dependencies(root):
    lock = read_json(root / "release/dependencies.json")
    require(
        set(lock) == {"mihomo", "curl", "zashboard"},
        "Unexpected dependency lock entries",
    )
    for name, item in lock.items():
        require(
            re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), f"Missing SHA-256 for {name}"
        )
        if name == "curl":
            revision = item["revision"]
            require(
                re.fullmatch(r"[0-9a-f]{40}", revision),
                "curl needs an immutable source revision",
            )
            expected = f"https://raw.githubusercontent.com/Zackptg5/Cross-Compiled-Binaries-Android/{revision}/curl/curl-arm64"
        else:
            require(
                re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", item["version"]),
                f"Pin a release version for {name}",
            )
            version = item["version"]
            expected = (
                f"https://github.com/MetaCubeX/mihomo/releases/download/{version}/mihomo-android-arm64-v8-{version}.gz"
                if name == "mihomo"
                else f"https://github.com/Zephyruso/zashboard/releases/download/{version}/dist.zip"
            )
        require(
            item["url"] == expected, f"Unexpected or unpinned download URL for {name}"
        )
    return lock


def check(root, tag=None):
    prop = version_settings(root)
    require(
        read_json(root / "Surfing.json") == update_manifest(metadata(prop)),
        "Surfing.json is stale; run tools/release.py sync",
    )
    release_notes(root, prop["version"])
    dependencies(root)
    if tag is not None:
        require(
            tag == prop["version"], "Release tag must exactly match module.prop version"
        )
    return prop


def safe_name(name):
    path = PurePosixPath(name)
    return (
        bool(name)
        and not path.is_absolute()
        and not any(x in ("..", ".", "") for x in name.split("/"))
        and "\\" not in name
        and ":" not in name
    )


def private_name(name):
    return name == "box_bll/clash/private" or name.startswith("box_bll/clash/private/")


def payload_name(name):
    return (
        safe_name(name)
        and not private_name(name)
        and not name.endswith((".bak", ".log", ".gitkeep"))
        and (
            name in ROOT_PAYLOAD
            or name.startswith(("META-INF/", "webroot/", "box_bll/"))
        )
    )


def git(root, *args):
    return (
        subprocess.check_output(["git", "-C", str(root), *args])
        .decode("utf-8")
        .rstrip("\r\n")
    )


def source_record(root):
    if (root / SNAPSHOT).is_file():
        record = read_json(root / SNAPSHOT)
        files = record["files"]
        for name, digest in files.items():
            require(
                safe_name(name) and not private_name(name),
                "Invalid source snapshot path",
            )
            path = root / name
            require(
                path.is_file() and not path.is_symlink() and file_hash(path) == digest,
                "Source snapshot changed; create a fresh snapshot",
            )
    else:
        require(
            Path(git(root, "rev-parse", "--show-toplevel")).resolve() == root.resolve(),
            "Build from the repository root or a release.py snapshot",
        )
        names = git(
            root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"
        ).split("\0")
        files = {}
        for name in sorted(set(names) - {""}):
            require(
                safe_name(name) and not private_name(name),
                "Private or unsafe path in source inventory",
            )
            path = root / name
            require(
                not path.is_symlink(), "Symlinks are not supported in release sources"
            )
            if path.is_file():
                files[name] = file_hash(path)
        record = {
            "commit": git(root, "rev-parse", "HEAD"),
            "dirty": bool(git(root, "status", "--porcelain", "--untracked-files=all")),
            "epoch": int(git(root, "show", "-s", "--format=%ct", "HEAD")),
            "files": files,
        }
    require(re.fullmatch(r"[0-9a-f]{40}", record["commit"]), "Invalid source commit")
    require(type(record["dirty"]) is bool, "Invalid source dirty flag")
    record["treeSha256"] = sha256(encoded(files))
    return record


def snapshot(root, destination):
    require(not destination.exists(), "Snapshot destination must not already exist")
    require(
        root.resolve() not in destination.resolve().parents,
        "Snapshot must be outside the workspace",
    )
    record = source_record(root)
    destination.mkdir(parents=True)
    for name in record["files"]:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    (destination / SNAPSHOT).write_bytes(encoded(record))
    return record


def download(item, cache):
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / item["sha256"]
    if not destination.exists():
        for attempt in range(3):
            try:
                request = urllib.request.Request(
                    item["url"], headers={"User-Agent": "Surfing-release-build"}
                )
                with urllib.request.urlopen(request, timeout=45) as response:
                    data = response.read()
                require(sha256(data) == item["sha256"], "Dependency checksum mismatch")
                # Concurrent builds never observe partially downloaded cache entries.
                with tempfile.NamedTemporaryFile(dir=cache, delete=False) as handle:
                    pending = Path(handle.name)
                    handle.write(data)
                pending.replace(destination)
                break
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise ReleaseError(
                        "Dependency download failed; no release was published"
                    ) from None
                time.sleep(attempt + 1)
    require(
        file_hash(destination) == item["sha256"], "Dependency cache checksum mismatch"
    )
    return destination.read_bytes()


def arm64_elf(data, name):
    require(
        data[:6] == b"\x7fELF\x02\x01" and data[18:20] == b"\xb7\x00",
        f"{name} must be an Android ARM64 ELF",
    )


def zip_bytes(entries, epoch):
    stream = io.BytesIO()
    stamp = time.gmtime(max(315532800, epoch))[:6]
    with zipfile.ZipFile(
        stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, data in sorted(entries.items()):
            require(safe_name(name), "Unsafe ZIP entry")
            info = zipfile.ZipInfo(name, stamp)
            info.create_system = 3
            executable = name.startswith(
                ("box_bll/bin/", "box_bll/scripts/")
            ) or name in {
                "customize.sh",
                "Surfing_service.sh",
                "uninstall.sh",
                "META-INF/com/google/android/update-binary",
            }
            info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)
    return stream.getvalue()


def zashboard_files(data):
    entries = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        require(archive.testzip() is None, "Zashboard ZIP CRC failed")
        for item in archive.infolist():
            require(
                safe_name(item.filename.rstrip("/"))
                and not stat.S_ISLNK(item.external_attr >> 16),
                "Unsafe Zashboard ZIP entry",
            )
            if not item.is_dir():
                require(
                    item.filename.startswith("dist/"), "Unexpected Zashboard ZIP layout"
                )
                name = "box_bll/clash/webroot/Zash/" + item.filename.removeprefix(
                    "dist/"
                )
                require(name not in entries, "Duplicate Zashboard ZIP entry")
                entries[name] = archive.read(item)
    require(
        "box_bll/clash/webroot/Zash/index.html" in entries,
        "Zashboard index.html is missing",
    )
    return entries


def tile_payload(root, epoch):
    directory = root / "app/version/com.github.surfing"
    entry = read_json(directory / "release.json")[0]
    require(
        re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", entry["versionName"]),
        "Unexpected SurfingTile version",
    )
    name = f"SurfingTile_{entry['versionName'][1:]}_release.apk"
    apk = (directory / name).read_bytes()
    require(
        len(apk) == entry["fileSize"] and sha256(apk) == entry["sha256"],
        "SurfingTile APK differs from its release manifest",
    )
    version = (
        f"versionCode={entry['versionCode']}\nversionName={entry['versionName']}\n"
    )
    packed = zip_bytes(
        {"com.github.surfing.apk": apk, "version": version.encode()}, epoch
    )
    return packed, {
        "version": entry["versionName"],
        "versionCode": entry["versionCode"],
        "sha256": entry["sha256"],
        "source": f"app/version/com.github.surfing/{name}",
    }


def build(root, channel, output, cache):
    prop = check(root)
    source = source_record(root)
    meta = metadata(prop, channel, source["commit"])
    lock = dependencies(root)
    entries = {
        name: (root / name).read_bytes()
        for name in source["files"]
        if payload_name(name) and not name.startswith("box_bll/clash/webroot/Zash/")
    }
    records = {}
    for name, item in lock.items():
        print(f"Verify dependency: {name} {item['version']}", flush=True)
        data = download(item, cache)
        records[name] = dict(item)
        if name == "zashboard":
            web = zashboard_files(data)
            entries.update(web)
            records[name]["treeSha256"] = sha256(
                encoded({key: sha256(value) for key, value in sorted(web.items())})
            )
        else:
            data = gzip.decompress(data) if name == "mihomo" else data
            arm64_elf(data, name)
            entries[f"box_bll/bin/{'clash' if name == 'mihomo' else 'curl'}"] = data
            records[name]["payloadSha256"] = sha256(data)
    busybox = entries["box_bll/bin/busybox"]
    arm64_elf(busybox, "busybox")
    busybox_version = re.search(rb"BusyBox v[^\x00\n ]+", busybox)
    require(busybox_version is not None, "BusyBox version is missing")
    records["busybox"] = {
        "version": busybox_version[0].decode("ascii"),
        "sha256": sha256(busybox),
        "source": "box_bll/bin/busybox",
    }
    entries["SurfingTile.zip"], records["surfingTile"] = tile_payload(
        root, source["epoch"]
    )
    prop["version"], prop["versionCode"] = meta["version"], str(meta["versionCode"])
    entries["module.prop"] = (
        "".join(f"{key}={value}\n" for key, value in prop.items())
    ).encode("utf-8")
    info = {
        "schema": 1,
        "repository": REPOSITORY,
        **meta,
        "source": {key: value for key, value in source.items() if key != "files"},
        "toolchain": {"python": platform.python_version(), "zlib": zlib.ZLIB_VERSION},
        "dependencies": records,
        "payload": {name: sha256(value) for name, value in sorted(entries.items())},
    }
    entries["build-info.json"] = encoded(info)
    notes = release_notes(root, meta["baseVersion"])
    notes += (
        f"\nSource: `{source['commit']}`; dirty: `{str(source['dirty']).lower()}`.\n"
    )
    notes += f"\nChannel: {channel}; versionCode: {meta['versionCode']}. See build-info.json and SHA256SUMS for provenance.\n"
    assets = {
        meta["zipName"]: zip_bytes(entries, source["epoch"]),
        "build-info.json": encoded(info),
        "changelog.md": notes.encode("utf-8"),
    }
    if channel == "stable":
        assets["Surfing.json"] = encoded(update_manifest(meta))
    assets["SHA256SUMS"] = "".join(
        f"{sha256(data)}  {name}\n" for name, data in sorted(assets.items())
    ).encode()
    output.mkdir(parents=True, exist_ok=True)
    require(
        not ({p.name for p in output.iterdir()} - set(assets)),
        "Output contains other versions or files; use a fresh directory",
    )
    for name, data in assets.items():
        # Replace complete files; never update an old ZIP with stale excluded entries.
        with tempfile.NamedTemporaryFile(dir=output, delete=False) as handle:
            pending = Path(handle.name)
            handle.write(data)
        pending.replace(output / name)
    verify(output, root)
    return info


def verify(output, root=None):
    info = read_json(output / "build-info.json")
    require(
        info["schema"] == 1 and info["repository"] == REPOSITORY,
        "Unexpected release bundle",
    )
    meta = metadata(
        {"version": info["baseVersion"], "versionCode": str(info["stableVersionCode"])},
        info["channel"],
        info["source"]["commit"],
    )
    require(
        all(info[key] == value for key, value in meta.items()),
        "Inconsistent release identity",
    )
    require(re.fullmatch(VERSION_RE, info["baseVersion"]), "Unexpected release version")
    require(
        1653 < info["stableVersionCode"] <= 2147483647, "Invalid stable versionCode"
    )
    expected = {info["zipName"], "build-info.json", "changelog.md", "SHA256SUMS"}
    if info["channel"] == "stable":
        expected.add("Surfing.json")
        require(
            read_json(output / "Surfing.json") == update_manifest(meta),
            "Update manifest does not match this ZIP and tag",
        )
    require(
        {path.name for path in output.iterdir()} == expected,
        "Unexpected or missing release assets",
    )
    sums = {}
    for line in (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        require(
            name in expected - {"SHA256SUMS"} and name not in sums,
            "Invalid checksum entry",
        )
        require(file_hash(output / name) == digest, "Release asset SHA-256 mismatch")
        sums[name] = digest
    require(set(sums) == expected - {"SHA256SUMS"}, "Incomplete checksum list")
    with zipfile.ZipFile(output / info["zipName"]) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate module ZIP entry")
        require(REQUIRED <= set(names), "Module ZIP is missing required files")
        require(
            all(
                payload_name(name) or name in {"SurfingTile.zip", "build-info.json"}
                for name in names
            ),
            "Forbidden file in module ZIP",
        )
        require(
            all(
                not stat.S_ISLNK(item.external_attr >> 16)
                for item in archive.infolist()
            ),
            "Symlink in module ZIP",
        )
        require(archive.testzip() is None, "Module ZIP CRC failed")
        require(
            archive.read("build-info.json")
            == (output / "build-info.json").read_bytes(),
            "Embedded provenance differs",
        )
        require(
            set(info["payload"]) == set(names) - {"build-info.json"},
            "Incomplete payload inventory",
        )
        for name, digest in info["payload"].items():
            require(
                sha256(archive.read(name)) == digest, "Module payload SHA-256 mismatch"
            )
        prop = properties(archive.read("module.prop").decode("utf-8"))
        require(
            prop["id"] == "Surfing" and prop["updateJson"] == UPDATE_URL,
            "Incompatible module identity or update channel",
        )
        require(
            prop["version"] == info["version"]
            and int(prop["versionCode"]) == info["versionCode"],
            "Module and release versions differ",
        )
        for dependency, binary in (
            ("mihomo", "clash"),
            ("curl", "curl"),
            ("busybox", "busybox"),
        ):
            data = archive.read(f"box_bll/bin/{binary}")
            arm64_elf(data, binary)
            item = info["dependencies"][dependency]
            require(
                sha256(data) == item.get("payloadSha256", item["sha256"]),
                "Binary provenance mismatch",
            )
        with zipfile.ZipFile(io.BytesIO(archive.read("SurfingTile.zip"))) as tile:
            require(
                set(tile.namelist()) == {"version", "com.github.surfing.apk"}
                and len(tile.namelist()) == 2
                and tile.testzip() is None,
                "Invalid SurfingTile package",
            )
            item = info["dependencies"]["surfingTile"]
            require(
                sha256(tile.read("com.github.surfing.apk")) == item["sha256"],
                "SurfingTile checksum mismatch",
            )
            require(
                properties(tile.read("version").decode())
                == {
                    "versionName": item["version"],
                    "versionCode": str(item["versionCode"]),
                },
                "SurfingTile version mismatch",
            )
        web = {
            name: info["payload"][name]
            for name in names
            if name.startswith("box_bll/clash/webroot/Zash/")
        }
        require(
            sha256(encoded(web)) == info["dependencies"]["zashboard"]["treeSha256"],
            "Zashboard provenance mismatch",
        )
    if root is not None:
        prop = check(root)
        require(
            meta == metadata(prop, info["channel"], info["source"]["commit"]),
            "Bundle differs from source release settings",
        )
        record = source_record(root)
        require(
            info["source"]
            == {key: value for key, value in record.items() if key != "files"},
            "Bundle differs from current source snapshot",
        )
        for name, item in dependencies(root).items():
            require(
                all(
                    info["dependencies"][name][key] == value
                    for key, value in item.items()
                ),
                "Bundle differs from dependency lock",
            )
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="Generate the checked-in stable manifest preview")
    checker = sub.add_parser(
        "check", help="Check version, tag, manifest and dependency pins"
    )
    checker.add_argument("--tag")
    copier = sub.add_parser(
        "snapshot",
        help="Copy current source bytes outside the workspace, without Git or private files",
    )
    copier.add_argument("destination", type=Path)
    builder = sub.add_parser("build")
    builder.add_argument("--channel", choices=("stable", "alpha"), default="stable")
    builder.add_argument("--output", type=Path)
    builder.add_argument(
        "--cache",
        type=Path,
        default=Path(tempfile.gettempdir()) / "surfing-release-dependencies",
    )
    verifier = sub.add_parser("verify")
    verifier.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "sync":
            (ROOT / "Surfing.json").write_bytes(
                encoded(update_manifest(metadata(version_settings(ROOT))))
            )
        elif args.command == "check":
            check(ROOT, args.tag)
        elif args.command == "snapshot":
            record = snapshot(ROOT, args.destination)
            print(
                f"Snapshot: {args.destination}; commit={record['commit']}; dirty={record['dirty']}"
            )
        elif args.command == "build":
            require(
                not any(
                    name in os.environ
                    for name in (
                        "isAlpha",
                        "MIHOMO_VERSION",
                        "ZASH_VERSION",
                        "SHORT_HASH",
                    )
                ),
                "Legacy build overrides are not supported; use --channel and release/dependencies.json",
            )
            result = build(
                ROOT,
                args.channel,
                args.output or ROOT / "dist" / args.channel,
                args.cache,
            )
            print(
                f"Built and verified: {result['zipName']}; source dirty={result['source']['dirty']}"
            )
        elif args.command == "verify":
            verify(args.directory, ROOT)
        print("Release checks passed.")
    except (
        ReleaseError,
        ValueError,
        KeyError,
        OSError,
        subprocess.CalledProcessError,
        zipfile.BadZipFile,
    ) as error:
        parser.exit(1, f"Release error: {error}\n")


if __name__ == "__main__":
    main()

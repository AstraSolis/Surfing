#!/bin/sh

set -e

isAlpha="${isAlpha:-false}"

CORE_DST="box_bll/bin/clash"
CORE_TMP="clash_core.gz"
MIHOMO_API="https://api.github.com/repos/MetaCubeX/mihomo/releases/latest"
MIHOMO_BASE="https://github.com/MetaCubeX/mihomo/releases/download"
MIHOMO_NAME="mihomo-android-arm64-v8"

CURL_DST="box_bll/bin/curl"
CURL_TMP="curl_tmp"
CURL_URL="https://raw.githubusercontent.com/Zackptg5/Cross-Compiled-Binaries-Android/master/curl/curl-arm64"

ZASH_API="https://api.github.com/repos/Zephyruso/zashboard/releases/latest"
ZASH_DST="box_bll/clash/webroot/Zash"
ZASH_TMP="zash_dist.zip"

get_latest_tag() {
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        set -- -H "Authorization: Bearer $GITHUB_TOKEN" "$1"
    fi
    curl -fsSL --retry 5 --retry-delay 5 \
        "$@" \
        | grep '"tag_name":' | head -n 1 \
        | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/'
}

# 可显式固定版本以复现构建；未指定时保持获取最新版本的行为。
latest_version=${MIHOMO_VERSION:-$(get_latest_tag "$MIHOMO_API")}

if [ -z "$latest_version" ]; then
    echo "Error: Failed to fetch Mihomo version."
    exit 1
fi

echo "Latest Mihomo version: $latest_version"

download_url="${MIHOMO_BASE}/${latest_version}/${MIHOMO_NAME}-${latest_version}.gz"

echo "Downloading Mihomo core..."
if curl -fL --retry 5 --retry-delay 5 "$download_url" -o "$CORE_TMP"; then
    gunzip -c "$CORE_TMP" > "$CORE_DST"
    rm -f "$CORE_TMP"
    chmod +x "$CORE_DST"
else
    echo "Error: Mihomo download failed."
    exit 1
fi

echo "Downloading curl..."
if curl -fL --retry 5 --retry-delay 5 "$CURL_URL" -o "$CURL_TMP"; then
    mv -f "$CURL_TMP" "$CURL_DST"
    chmod +x "$CURL_DST"
else
    echo "Error: curl download failed."
    exit 1
fi

zash_latest_version=${ZASH_VERSION:-$(get_latest_tag "$ZASH_API")}
if [ -n "$zash_latest_version" ]; then
    echo "Latest Zashboard version: $zash_latest_version"
    zash_url="https://github.com/Zephyruso/zashboard/releases/download/${zash_latest_version}/dist.zip"
    echo "Downloading Zashboard..."
    if curl -fL --retry 5 --retry-delay 5 "$zash_url" -o "$ZASH_TMP"; then
        rm -rf dist Zash "$ZASH_DST"
        mkdir -p "$(dirname "$ZASH_DST")"
        unzip -q "$ZASH_TMP" -d "./zash_temp"
        if [ -d "./zash_temp/dist" ]; then
            mv "./zash_temp/dist" "$ZASH_DST"
            echo "Zashboard deployed to $ZASH_DST"
        else
            echo "Error: Unexpected ZIP structure in Zashboard."
            exit 1
        fi
        rm -rf zash_temp "$ZASH_TMP"
    else
        echo "Error: Zashboard download failed."
        exit 1
    fi
else
    echo "Error: Failed to fetch Zashboard version."
    exit 1
fi

APK_DIR="app/version/com.github.surfing"
TILE_ZIP="SurfingTile.zip"
TILE_STAGE=".tile_stage"

rm -rf "$TILE_STAGE" "$TILE_ZIP"
mkdir -p "$TILE_STAGE"
latest_apk=$(find "$APK_DIR" -maxdepth 1 -name "SurfingTile_*_release.apk" 2>/dev/null | sort -V | tail -n 1)
if [ -f "$latest_apk" ]; then
    cp -f "$latest_apk" "$TILE_STAGE/com.github.surfing.apk"
    TILE_CODE=$(awk -F: '/versionCode/ {gsub(/[^0-9]/, "", $2); print $2; exit}' "$APK_DIR/release.json" 2>/dev/null)
    TILE_NAME=$(awk -F'"' '/versionName/ {print $4; exit}' "$APK_DIR/release.json" 2>/dev/null)
    printf 'versionCode=%s\nversionName=%s\n' "$TILE_CODE" "$TILE_NAME" > "$TILE_STAGE/version"
    (cd "$TILE_STAGE" && zip -r -o -X "../$TILE_ZIP" ./*)
fi
rm -rf "$TILE_STAGE"

version=$(grep '^version=' module.prop | awk -F '=' '{print $2}' | sed 's/ (.*//')
short_hash=${SHORT_HASH:-$(git rev-parse --short=7 HEAD)}

if [ "$isAlpha" = "true" ]; then
    new_version="${version} (alpha-${short_hash})"
    filename="Surfing_alpha_${short_hash}.zip"
else
    new_version="${version} (release-${short_hash})"
    filename="Surfing_${version}_release.zip"
fi

sed -i "s/^version=.*/version=${new_version}/" module.prop

# zip 默认更新已有文件，排除项不会删除旧条目；必须重新创建归档。
rm -f "$filename"
zip -r -o -X "$filename" ./ \
    -x 'app/*' \
    -x '.git/*' \
    -x '.github/*' \
    -x '.idea/*' \
    -x '.ruff_cache/*' \
    -x '.gitignore' \
    -x 'AGENTS.md' \
    -x 'Surfing_*.zip' \
    -x 'box_bll/clash/private/*' \
    -x 'tests/*' \
    -x 'folder/*' \
    -x 'build.sh' \
    -x 'Surfing.json' \

echo "Build Completed: $filename"
# Host-side Android API stubs. All device paths are rewritten into a temporary root.
ui_print() { printf '%s\n' "$*"; }
abort() {
    printf '%s\n' "$*" >&2
    exit 1
}
magisk() { echo 30.0; }
unzip() { :; } # The test pre-populates the extracted module tree.
pm() { return 1; }
dumpsys() { echo versionCode=999999; }
settings() { :; }
pidof() { :; }
nohup() { :; }
sleep() { :; }
timeout() {
    shift
    "$@"
}
getevent() {
    keypress_index=$(cat "$KEY_INDEX")
    keypress_index=$((keypress_index + 1))
    echo "$keypress_index" > "$KEY_INDEX"
    key=$(sed -n "${keypress_index}p" "$KEYS")
    printf 'EV_KEY %s DOWN\n' "$key"
}
set_perm() {
    printf 'single %s %s\n' "$1" "$4" >> "$PERM_LOG"
    chmod "$4" "$1"
}
set_perm_recursive() {
    printf 'recursive %s %s %s\n' "$1" "$4" "$5" >> "$PERM_LOG"
    find "$1" -type d -exec chmod "$4" {} +
    find "$1" -type f -exec chmod "$5" {} +
}
# The Python harness supplies the rewritten installer in a temporary directory.
# shellcheck disable=SC1090
. "$INSTALLER"

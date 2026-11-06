#!/bin/sh

set -eu
cd "$(dirname "$0")"

# Python verifies pinned dependencies, creates a fresh ZIP and checks the bundle.
# Use a release.py snapshot when testing local edits; never package device data.
exec "${PYTHON:-python3}" tools/release.py build "$@"

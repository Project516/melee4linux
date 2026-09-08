#!/bin/sh
# Run a packaged app from Terminal. Finder can open the same app directly.
set -eu
if [ "$#" -lt 1 ]; then
    echo 'Usage: native/macos/run.sh "/path/to/Melee for Mac.app" [runtime options]' >&2
    exit 2
fi
app=$1
shift
if [ ! -x "$app/Contents/MacOS/Melee" ]; then
    echo "Melee launcher not found in: $app" >&2
    exit 1
fi
exec "$app/Contents/MacOS/Melee" "$@"

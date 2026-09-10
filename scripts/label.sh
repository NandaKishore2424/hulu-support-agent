#!/usr/bin/env bash
# Serve the labelling page over http so the browser allows localStorage.
# Opening data/golden/label.html by double-click puts it on a file:// origin
# where storage is blocked and progress cannot be saved.
set -euo pipefail
cd "$(dirname "$0")/../data/golden"
PORT="${PORT:-8777}"
PAGE="${PAGE:-label.html}"
echo "UI: http://localhost:${PORT}/${PAGE}"
echo "press ctrl-c when you have exported golden_labels.jsonl"
exec python3 -m http.server "$PORT" --bind 127.0.0.1

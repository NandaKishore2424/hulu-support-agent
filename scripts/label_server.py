"""Serve the labelling pages and persist every label to disk as it is made.

The first version relied on the browser holding an hour of labelling in
localStorage until the user pressed export. That put the most expensive artefact
in the project behind a single button and a storage API that returns nothing at
all in a private window, after a site-data clear, or on a file:// origin. It
produced a 200-row export containing no labels and no error.

This server removes the dependency. Every label is POSTed the moment it is
entered and written straight to data/golden/, so the file on disk is always
current and pressing export is optional.

Usage:  python scripts/label_server.py
        then open http://localhost:8777/label.html
"""
from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "golden"
# Only these names may be written, so a page cannot talk the server into
# overwriting source files.
ALLOWED = {"golden_labels.jsonl", "reply_ratings.jsonl", "spotcheck_labels.jsonl"}
PORT = 8777


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def do_POST(self) -> None:                      # noqa: N802 - stdlib naming
        if self.path != "/save":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            name = body.get("file", "")
            rows = body.get("rows", [])
            if name not in ALLOWED or not isinstance(rows, list):
                self.send_error(400, "bad file or rows")
                return
            complete = [r for r in rows if _is_complete(name, r)]
            (ROOT / name).write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                encoding="utf-8")
            payload = json.dumps({"saved": len(rows), "complete": len(complete)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            print(f"  saved {name}: {len(complete)}/{len(rows)} complete", flush=True)
        except Exception as exc:                    # noqa: BLE001
            self.send_error(500, str(exc)[:200])

    def log_message(self, *a) -> None:              # quiet the per-request noise
        pass


def _is_complete(name: str, row: dict) -> bool:
    if name in ("golden_labels.jsonl", "spotcheck_labels.jsonl"):
        return bool(row.get("intent")) and bool(row.get("handling"))
    return all(k in row for k in ("grounded", "actionable", "safe", "voice", "usable"))


def main() -> None:
    if not ROOT.exists():
        sys.exit(f"missing {ROOT}")
    print(f"serving {ROOT} on http://localhost:{PORT}")
    print("  labelling  http://localhost:8777/label.html")
    print("  rating     http://localhost:8777/rate.html")
    print("every label is written to disk as you go; export is optional")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Push today's generated post candidates to a Google Sheet via an
Apps Script webhook (see docs/sheet-webhook-setup.md for the GAS code).

Environment:
    SHEET_WEBHOOK_URL   Apps Script Web App URL. If unset, exits silently
                        (so CI works before the sheet is set up).

Usage:
    python3 scripts/push_candidates_to_sheet.py
    python3 scripts/push_candidates_to_sheet.py --date 2026-07-30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "output" / "posts"
JST = timezone(timedelta(hours=9))

TYPE_LABELS = {"nichijo": "日常", "ninchi": "認知", "shinrai": "信頼(要差し替え)"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    args = parser.parse_args()

    url = (os.environ.get("SHEET_WEBHOOK_URL") or "").strip()
    if not url:
        print("SHEET_WEBHOOK_URL not set — skipping sheet push")
        return 0

    date_str = args.date or datetime.now(JST).strftime("%Y-%m-%d")
    posts_file = POSTS_DIR / f"{date_str}.json"
    if not posts_file.exists():
        print(f"ERROR: {posts_file} not found", file=sys.stderr)
        return 1

    items = json.loads(posts_file.read_text(encoding="utf-8"))
    rows = [
        [date_str, it["slug"], TYPE_LABELS.get(it.get("type", ""), it.get("type", "")), it["text"], ""]
        for it in items
    ]
    payload = json.dumps({"date": date_str, "rows": rows}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    print(f"pushed {len(rows)} rows to sheet: {body[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

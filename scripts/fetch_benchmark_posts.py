#!/usr/bin/env python3
"""
Fetch benchmark X posts from the benchmark Google Sheet.

The sheet has two data tabs (auto-populated by an external scraper):
  - gid 951461315:  ベンチマークアカウントの直近投稿
  - gid 1746582074: 同属性アカウントのバズ投稿

Output:
  reference/benchmark_posts.json  (source of truth, used by generate_daily_posts.py)
  reference/benchmark-digest.md   (human-readable digest)

Environment:
    BENCHMARK_SHEET_ID  optional, defaults to the shared benchmark sheet

Usage:
    python3 scripts/fetch_benchmark_posts.py
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = REPO_ROOT / "reference"
JSON_PATH = REFERENCE_DIR / "benchmark_posts.json"
DIGEST_PATH = REFERENCE_DIR / "benchmark-digest.md"

DEFAULT_SHEET_ID = "1dX0anG-0Q8u6o1yxtwPaWFf1zu-XGLeRFvZcHoO9hDI"
GID_BENCHMARK = 951461315   # ベンチマークアカウント直近投稿
GID_BUZZ = 1746582074       # 同属性アカウントのバズ投稿

JST = timezone(timedelta(hours=9))

URL_RE = re.compile(r"https?://t\.co/\S+")


def fetch_csv(sheet_id: str, gid: int) -> list[dict]:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    if raw.lstrip().startswith("<!DOCTYPE"):
        raise RuntimeError(f"gid={gid} returned HTML — sheet not public or gid wrong")
    return list(csv.DictReader(io.StringIO(raw)))


def to_int(v: str) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def clean_text(t: str) -> str:
    t = URL_RE.sub("", t or "").strip()
    return re.sub(r"\n{3,}", "\n\n", t)


def parse_rows(rows: list[dict]) -> list[dict]:
    posts = []
    for r in rows:
        if (r.get("isRetweet") or "").lower() == "true":
            continue
        text = clean_text(r.get("fullText") or r.get("text") or "")
        if not text:
            continue
        try:
            created = datetime.strptime(
                r.get("createdAt", ""), "%a %b %d %H:%M:%S %z %Y"
            ).astimezone(JST).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            created = r.get("createdAt", "")
        posts.append(
            {
                "user": r.get("author/userName", ""),
                "followers": to_int(r.get("author/followers")),
                "text": text,
                "likes": to_int(r.get("likeCount")),
                "retweets": to_int(r.get("retweetCount")),
                "views": to_int(r.get("viewCount")),
                "is_reply": (r.get("isReply") or "").lower() == "true",
                "created_at": created,
            }
        )
    return posts


def main() -> None:
    sheet_id = os.environ.get("BENCHMARK_SHEET_ID", DEFAULT_SHEET_ID)
    benchmark = parse_rows(fetch_csv(sheet_id, GID_BENCHMARK))
    buzz = parse_rows(fetch_csv(sheet_id, GID_BUZZ))
    buzz.sort(key=lambda p: p["likes"], reverse=True)

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    JSON_PATH.write_text(
        json.dumps(
            {"fetched_at": fetched_at, "benchmark": benchmark, "buzz": buzz},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    lines = [
        "# ベンチマーク投稿ダイジェスト",
        f"取得: {fetched_at} / ベンチマーク {len(benchmark)}件・バズ {len(buzz)}件",
        "",
        "## バズ投稿 TOP20（同属性アカウント）",
        "",
    ]
    for p in buzz[:20]:
        lines.append(f"- ❤️{p['likes']} 👁{p['views']} @{p['user']}: {p['text'][:120]}")
    lines += ["", "## ベンチマークアカウント別 最新投稿", ""]
    seen = set()
    for p in benchmark:
        if p["user"] in seen:
            continue
        seen.add(p["user"])
        lines.append(f"- @{p['user']}: {p['text'][:120]}")
    DIGEST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"saved {len(benchmark)} benchmark / {len(buzz)} buzz posts -> {JSON_PATH.name}, {DIGEST_PATH.name}")


if __name__ == "__main__":
    main()

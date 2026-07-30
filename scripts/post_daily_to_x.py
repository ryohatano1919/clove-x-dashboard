#!/usr/bin/env python3
"""
Multi-account X auto-poster.

Posts each account's daily generated post (output/posts/{date}.json,
created by generate_daily_posts.py) to X via the X API v2, using
per-account credentials.

Credentials:
    accounts/{slug}/x_credentials.env   (gitignored)
        X_API_KEY=...
        X_API_SECRET=...
        X_ACCESS_TOKEN=...
        X_ACCESS_TOKEN_SECRET=...

Flow (run from cron/launchd):
    1. plan : build today's schedule with a randomized post time per
              account (within its allowed time bands). Idempotent —
              won't overwrite an existing schedule.
    2. run  : post every entry whose time has passed and which hasn't
              been posted yet. Safe to call every 10 minutes.

Usage:
    python3 scripts/post_daily_to_x.py plan
    python3 scripts/post_daily_to_x.py run
    python3 scripts/post_daily_to_x.py run --dry-run
    python3 scripts/post_daily_to_x.py status
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = REPO_ROOT / "accounts"
POSTS_DIR = REPO_ROOT / "output" / "posts"
SCHEDULE_DIR = REPO_ROOT / "output" / "schedule"

JST = timezone(timedelta(hours=9))

# Posting windows (JST hour ranges) rotated per account so the fleet
# never posts in a burst. Each account gets a random minute too.
TIME_BANDS = [
    (8, 10),    # 朝
    (12, 13),   # 昼休み
    (17, 19),   # 夕方
    (19, 21),   # 夜前半
    (21, 23),   # 夜後半
]


def load_credentials(slug: str) -> dict | None:
    path = ACCOUNTS_DIR / slug / "x_credentials.env"
    if not path.exists():
        return None
    creds = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        creds[k.strip()] = v.strip().strip('"').strip("'")
    required = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    if not all(creds.get(k) for k in required):
        return None
    return creds


def schedule_path(date_str: str) -> Path:
    return SCHEDULE_DIR / f"{date_str}.json"


def cmd_plan(date_str: str, only: set[str] | None = None) -> int:
    """Assign each account with credentials a random post time today."""
    sched_file = schedule_path(date_str)
    if sched_file.exists():
        print(f"Schedule already exists: {sched_file.relative_to(REPO_ROOT)} (not overwriting)")
        return 0

    posts_file = POSTS_DIR / f"{date_str}.json"
    if not posts_file.exists():
        print(f"ERROR: no posts file {posts_file}. Run generate_daily_posts.py first.", file=sys.stderr)
        return 1
    all_posts = json.loads(posts_file.read_text(encoding="utf-8"))
    # 信頼型(当選報告)はカード名・金額を実物に差し替える前提のドラフト — 自動投稿しない
    drafts = [p["slug"] for p in all_posts if p.get("draft")]
    posts = {p["slug"]: p["text"] for p in all_posts if not p.get("draft")}

    entries = []
    skipped = []
    slugs = sorted(posts.keys())
    if only:
        slugs = [s for s in slugs if s in only]
        if not slugs:
            print(f"ERROR: none of {sorted(only)} found in {posts_file.name}", file=sys.stderr)
            return 1
    random.shuffle(slugs)
    for i, slug in enumerate(slugs):
        if load_credentials(slug) is None:
            skipped.append(slug)
            continue
        lo, hi = TIME_BANDS[i % len(TIME_BANDS)]
        hour = random.randint(lo, hi - 1)
        minute = random.randint(0, 59)
        entries.append({
            "slug": slug,
            "time": f"{hour:02d}:{minute:02d}",
            "text": posts[slug],
            "status": "pending",
        })

    entries.sort(key=lambda e: e["time"])
    SCHEDULE_DIR.mkdir(parents=True, exist_ok=True)
    sched_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Planned {len(entries)} posts -> {sched_file.relative_to(REPO_ROOT)}")
    if skipped:
        print(f"Skipped (no credentials): {', '.join(sorted(skipped))}")
    if drafts:
        print(f"Draft (当選報告・手動差し替え待ち): {', '.join(sorted(drafts))}")
    return 0


def post_to_x(creds: dict, text: str) -> dict:
    import tweepy
    client = tweepy.Client(
        consumer_key=creds["X_API_KEY"],
        consumer_secret=creds["X_API_SECRET"],
        access_token=creds["X_ACCESS_TOKEN"],
        access_token_secret=creds["X_ACCESS_TOKEN_SECRET"],
    )
    response = client.create_tweet(text=text)
    return response.data or {}


def cmd_run(date_str: str, dry_run: bool) -> int:
    sched_file = schedule_path(date_str)
    if not sched_file.exists():
        print(f"No schedule for {date_str}. Run 'plan' first.")
        return 0

    entries = json.loads(sched_file.read_text(encoding="utf-8"))
    now_hm = datetime.now(JST).strftime("%H:%M")
    changed = False

    for e in entries:
        if e["status"] != "pending" or e["time"] > now_hm:
            continue
        creds = load_credentials(e["slug"])
        if creds is None:
            e["status"] = "error:no_credentials"
            changed = True
            continue
        if dry_run:
            print(f"[DRY] {e['slug']} @{e['time']}: {e['text'][:40]}...")
            continue
        try:
            result = post_to_x(creds, e["text"])
            e["status"] = "posted"
            e["tweet_id"] = str(result.get("id", ""))
            e["posted_at"] = datetime.now(JST).isoformat()
            print(f"[POSTED] {e['slug']} @{e['time']} tweet_id={e.get('tweet_id')}")
        except Exception as ex:
            e["status"] = f"error:{type(ex).__name__}"
            e["error"] = str(ex)[:300]
            print(f"[ERROR] {e['slug']}: {ex}", file=sys.stderr)
        changed = True

    if changed and not dry_run:
        sched_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    remaining = sum(1 for e in entries if e["status"] == "pending")
    print(f"Done. pending={remaining}")
    return 0


def cmd_status(date_str: str) -> int:
    sched_file = schedule_path(date_str)
    if not sched_file.exists():
        print(f"No schedule for {date_str}.")
        return 0
    for e in json.loads(sched_file.read_text(encoding="utf-8")):
        print(f"{e['time']}  {e['slug']:8s}  {e['status']:20s}  {e['text'][:40]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["plan", "run", "status"])
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today JST)")
    parser.add_argument("--only", default=None, help="Plan only these slugs (comma-separated)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    date_str = args.date or datetime.now(JST).strftime("%Y-%m-%d")
    if args.command == "plan":
        only = set(args.only.split(",")) if args.only else None
        return cmd_plan(date_str, only)
    if args.command == "run":
        return cmd_run(date_str, args.dry_run)
    return cmd_status(date_str)


if __name__ == "__main__":
    sys.exit(main())

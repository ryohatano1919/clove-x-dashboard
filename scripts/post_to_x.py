#!/usr/bin/env python3
"""
X (Twitter) auto-poster as a Clove user persona.

Reads persona/examples/rules from reference/ and recent post log,
generates a single post via Claude API, and posts to X via X API v2.

Environment variables required:
    ANTHROPIC_API_KEY
    X_API_KEY
    X_API_SECRET
    X_ACCESS_TOKEN
    X_ACCESS_TOKEN_SECRET

Usage:
    python post_to_x.py            # generate and post
    python post_to_x.py --dry-run  # generate only, don't post
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic
import tweepy

REPO_ROOT = Path(__file__).resolve().parent.parent
PERSONA_PATH = REPO_ROOT / "reference" / "x-user-persona.md"
EXAMPLES_PATH = REPO_ROOT / "reference" / "x-post-examples.md"
RULES_PATH = REPO_ROOT / "reference" / "x-post-rules.md"
LOG_PATH = REPO_ROOT / "output" / "content" / "x-post-log.md"

CLAUDE_MODEL = "claude-haiku-4-5"
RECENT_POST_WINDOW = 20
JST = timezone(timedelta(hours=9))


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def extract_recent_posts(log_text: str, n: int) -> str:
    """Pull out the most recent N posts from the log file."""
    blocks = [b.strip() for b in log_text.split("---") if b.strip()]
    blocks = [b for b in blocks if b.startswith("##")]
    recent = blocks[-n:] if len(blocks) > n else blocks
    return "\n\n---\n\n".join(recent) if recent else "(まだ投稿履歴なし)"


def build_prompt(persona: str, examples: str, rules: str, recent: str, now_jst: datetime) -> str:
    hour = now_jst.hour
    if 8 <= hour < 11:
        timeband = "朝"
    elif 11 <= hour < 15:
        timeband = "昼"
    elif 15 <= hour < 19:
        timeband = "夕方"
    else:
        timeband = "夜"

    return f"""あなたはこれからX(Twitter)に投稿する一人のユーザーです。
以下のペルソナ・ルール・お手本を読み込み、**今この瞬間の投稿を1つだけ**生成してください。

# 現在
- 日時: {now_jst.strftime('%Y-%m-%d %H:%M')} JST
- 時間帯: {timeband}

# ペルソナ
{persona}

# 投稿ルール（最優先・絶対遵守）
{rules}

# お手本（このクオリティ・トーンを目指す）
{examples}

# 直近の投稿履歴（被らないように）
{recent}

---

# 出力指示

- 投稿本文のみを **1つだけ** 出力してください
- 前置き・コメント・解説・引用符は一切不要
- 改行は本文内に必要なら入れてOK
- 文字数は50〜140字
- 直近の投稿と話題・表現・出だしの言葉が被らないこと
- ハッシュタグは0〜2個まで、絵文字は0〜2個まで

それでは1投稿だけ出力してください:"""


def generate_post(now_jst: datetime) -> str:
    persona = read_text(PERSONA_PATH)
    examples = read_text(EXAMPLES_PATH)
    rules = read_text(RULES_PATH)
    recent = extract_recent_posts(read_text(LOG_PATH), RECENT_POST_WINDOW)

    if not persona or not rules:
        raise RuntimeError(
            f"Persona or rules file missing. Check {PERSONA_PATH} and {RULES_PATH}."
        )

    prompt = build_prompt(persona, examples, rules, recent, now_jst)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()

    text = text.strip('"').strip("「").strip("」").strip()
    if len(text) > 280:
        text = text[:280]
    return text


def post_to_x(text: str) -> dict:
    client = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    response = client.create_tweet(text=text)
    return response.data


def append_to_log(text: str, now_jst: datetime) -> None:
    timestamp = now_jst.strftime("%Y-%m-%d %H:%M:%S JST")
    entry = f"\n## {timestamp}\n{text}\n\n---\n"
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(entry)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Generate only; do not post.")
    args = parser.parse_args()

    now_jst = datetime.now(JST)
    print(f"[{now_jst.isoformat()}] Generating post...", flush=True)

    try:
        text = generate_post(now_jst)
    except Exception as e:
        print(f"ERROR generating post: {e}", file=sys.stderr)
        return 1

    print(f"--- GENERATED ({len(text)} chars) ---")
    print(text)
    print("--- END ---", flush=True)

    if args.dry_run:
        print("(dry-run: not posting)")
        return 0

    try:
        result = post_to_x(text)
    except Exception as e:
        print(f"ERROR posting to X: {e}", file=sys.stderr)
        return 2

    print(f"Posted: tweet_id={result.get('id') if result else 'unknown'}")
    append_to_log(text, now_jst)
    print(f"Log appended: {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

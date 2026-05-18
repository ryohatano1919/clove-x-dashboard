#!/usr/bin/env python3
"""
Generate 1 daily post for each persona under accounts/.

Posts are saved to accounts/{slug}/posts/{YYYY-MM-DD}.md
and a summary JSON to output/posts/{YYYY-MM-DD}.json (used by render_dashboard.py).

Environment:
    ANTHROPIC_API_KEY required.

Usage:
    python3 scripts/generate_daily_posts.py
    python3 scripts/generate_daily_posts.py --only f20_01,m30_01
    python3 scripts/generate_daily_posts.py --date 2026-05-19
    python3 scripts/generate_daily_posts.py --overwrite
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = REPO_ROOT / "accounts"
REFERENCE_DIR = REPO_ROOT / "reference"
RULES_PATH = REFERENCE_DIR / "x-post-rules.md"
EXAMPLES_PATH = REFERENCE_DIR / "x-post-examples.md"
OUTPUT_DIR = REPO_ROOT / "output" / "posts"

CLAUDE_MODEL = "claude-haiku-4-5"
JST = timezone(timedelta(hours=9))
RECENT_POST_WINDOW = 14


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def get_recent_posts(slug: str, n: int = RECENT_POST_WINDOW) -> str:
    """過去の投稿履歴から最新n件取得"""
    posts_dir = ACCOUNTS_DIR / slug / "posts"
    if not posts_dir.exists():
        return "(まだ投稿履歴なし)"
    md_files = sorted(posts_dir.glob("*.md"))
    recent = md_files[-n:]
    texts = [f.read_text(encoding="utf-8").strip() for f in recent]
    texts = [t for t in texts if t]
    return "\n\n---\n\n".join(texts) if texts else "(まだ投稿履歴なし)"


def build_post_prompt(persona: str, rules: str, examples: str, recent: str, now_jst: datetime) -> str:
    hour = now_jst.hour
    if 8 <= hour < 11:
        timeband = "朝"
    elif 11 <= hour < 15:
        timeband = "昼"
    elif 15 <= hour < 19:
        timeband = "夕方"
    else:
        timeband = "夜"

    return f"""あなたはこれから X(Twitter) に投稿する一人のユーザーです。
以下のペルソナ・ルール・お手本を読み込み、**今日の投稿を1つだけ**生成してください。

# 現在
- 日時: {now_jst.strftime('%Y-%m-%d %H:%M')} JST
- 時間帯: {timeband}

# ペルソナ
{persona}

# 投稿ルール(最優先・絶対遵守)
{rules}

# お手本(このクオリティ・トーンを目指す)
{examples}

# 直近の投稿履歴(被らないように)
{recent}

---

# 出力指示

- 投稿本文のみを **1つだけ** 出力
- 前置き・コメント・解説・引用符は一切不要
- 文字数は50〜140字
- 直近の投稿と話題・表現・出だしの言葉が被らないこと
- ハッシュタグは0〜2個まで、絵文字は0〜2個まで
- 必ずペルソナの口調・関心領域・職業感に沿うこと(性別・年代も)
- Clove名指しは10投稿のうち3〜4回程度の頻度なので、今日言及するかはペルソナと話題に応じて判断

それでは投稿を1つだけ出力してください:"""


def generate_post_for_account(client, slug: str, now_jst: datetime):
    persona_path = ACCOUNTS_DIR / slug / "persona.md"
    if not persona_path.exists():
        return None, f"persona missing: {persona_path}"

    persona = read_text(persona_path)
    rules = read_text(RULES_PATH)
    examples = read_text(EXAMPLES_PATH)
    recent = get_recent_posts(slug)

    prompt = build_post_prompt(persona, rules, examples, recent, now_jst)
    last_err = None
    for attempt in range(4):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            # メタな前置き(「投稿します」「生成します」など)が「---」区切りで入った場合、最後の本文だけ採用
            if "\n---\n" in text:
                text = text.split("\n---\n")[-1].strip()
            # 引用符等の除去
            text = text.strip('"').strip("「").strip("」").strip()
            if len(text) > 280:
                text = text[:280]
            return text, None
        except (anthropic.APIStatusError, anthropic.RateLimitError, anthropic.APIConnectionError) as e:
            last_err = e
            wait = 2 ** attempt + random.random()
            print(f"  [retry {attempt+1}/4] {type(e).__name__}: sleeping {wait:.1f}s", flush=True)
            time.sleep(wait)
    return None, f"all retries failed: {last_err}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date for posts (YYYY-MM-DD), default today JST", default=None)
    parser.add_argument("--only", help="Generate only for these slugs (comma-separated)", default=None)
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing posts for this date")
    args = parser.parse_args()

    if args.date:
        date_str = args.date
        now_jst = datetime.fromisoformat(f"{date_str}T12:00:00+09:00")
    else:
        now_jst = datetime.now(JST)
        date_str = now_jst.strftime("%Y-%m-%d")

    client = anthropic.Anthropic()
    target_slugs = set(args.only.split(",")) if args.only else None

    # ペルソナがあるアカウントだけを対象に
    all_slugs = sorted([
        d.name for d in ACCOUNTS_DIR.iterdir()
        if d.is_dir() and (d / "persona.md").exists()
    ]) if ACCOUNTS_DIR.exists() else []

    if not all_slugs:
        print("ERROR: no personas found. Run generate_personas.py first.", file=sys.stderr)
        return 1

    results = []
    for slug in all_slugs:
        if target_slugs and slug not in target_slugs:
            continue

        post_path = ACCOUNTS_DIR / slug / "posts" / f"{date_str}.md"
        if post_path.exists() and not args.overwrite:
            content = post_path.read_text(encoding="utf-8").strip()
            print(f"[SKIP] {slug} {date_str} (existing): {content[:50]}...")
            results.append({"slug": slug, "date": date_str, "text": content, "status": "existing"})
            continue

        print(f"[GEN] {slug} {date_str}...", flush=True)
        try:
            text, err = generate_post_for_account(client, slug, now_jst)
        except Exception as e:
            text = None
            err = str(e)

        if err:
            print(f"[ERROR] {slug}: {err}", file=sys.stderr)
            continue

        post_path.parent.mkdir(parents=True, exist_ok=True)
        post_path.write_text(text, encoding="utf-8")
        print(f"  -> {text}")
        results.append({"slug": slug, "date": date_str, "text": text, "status": "new"})

    # サマリJSON出力:
    #   --only 指定時は、既存のサマリJSONとマージして全アカ分を保持
    #   --only なし時は、results そのものを書き出す(全アカ走査済み)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = OUTPUT_DIR / f"{date_str}.json"
    if target_slugs and summary_path.exists():
        try:
            existing = json.loads(summary_path.read_text(encoding="utf-8"))
            existing_map = {e["slug"]: e for e in existing if isinstance(e, dict) and "slug" in e}
        except Exception:
            existing_map = {}
        for r in results:
            existing_map[r["slug"]] = r
        merged = sorted(existing_map.values(), key=lambda x: x.get("slug", ""))
        summary_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSummary updated (merged): {summary_path.relative_to(REPO_ROOT)} ({len(merged)} entries)")
    else:
        summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSummary written: {summary_path.relative_to(REPO_ROOT)} ({len(results)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

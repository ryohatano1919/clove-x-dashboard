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
import re
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
BENCHMARK_PATH = REFERENCE_DIR / "benchmark_posts.json"
OUTPUT_DIR = REPO_ROOT / "output" / "posts"

CLAUDE_MODEL = "claude-sonnet-5"
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


def get_benchmark_sample(n_bench: int = 8, n_buzz: int = 4) -> str:
    """ベンチマーク/バズ投稿からランダムサンプルを整形して返す(未取得なら空文字)"""
    if not BENCHMARK_PATH.exists():
        return ""
    try:
        data = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    bench = [p for p in data.get("benchmark", []) if not p.get("is_reply")]
    buzz = [p for p in data.get("buzz", []) if not p.get("is_reply")]
    lines = []
    if bench:
        lines.append("## ベンチマークアカウントの直近投稿(等身大のトーン)")
        for p in random.sample(bench, min(n_bench, len(bench))):
            lines.append(f"- @{p['user']}: {p['text'][:140]}")
    if buzz:
        lines.append("\n## 同属性アカウントのバズ投稿(伸びる話題・切り口)")
        for p in random.sample(buzz[:40], min(n_buzz, len(buzz[:40]))):
            lines.append(f"- ❤️{p['likes']} @{p['user']}: {p['text'][:140]}")
    return "\n".join(lines)


def build_post_prompt(persona: str, rules: str, examples: str, recent: str, now_jst: datetime, benchmark: str = "(サンプルなし)") -> str:
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

# リアル投稿サンプル(実在ユーザーの生投稿)
文体の崩し方・温度感・話題の解像度の基準として参考にする。
**文言のコピペ・言い換えでの流用は絶対禁止。** 雰囲気とリアリティの水準だけ吸収すること。
ペルソナと属性が違う投稿(VTuberファン・ソシャゲ勢など)の話題は真似しない。
{benchmark}

# 直近の投稿履歴(被らないように)
{recent}

---

# AI感の正体(絶対に避ける構造)

以下は「AIが書いたと一発でバレる」パターン。1つでも該当したら書き直すこと。

- **状況実況**: 「仕事終わり。」「昼休み。」など今の時間帯の報告から始める
- **予定の宣言**: 「〜しなきゃ」「〜してみるか」「明日は〜する予定」で締める
- **1投稿に要素を詰め込む**: 時間帯+予定+感想+口癖、のフルコース。人間は1投稿1トピック
- **口癖の接ぎ木**: ペルソナの口癖・特徴表現を無理に埋め込む。口癖は10投稿に1回出れば十分で、今日は使わなくていい
- **整いすぎた文**: 全文が主語述語の揃った完結文。実際のXは体言止め・言いさし・倒置・一文だけの投稿が多い
- **起承転結**: きれいにオチをつけようとする。オチのない「ただのぼやき」でいい

# 書き方のコツ

- 今日その人が「思わず呟いた一言」を書く。日記ではなくつぶやき
- 具体的なモノ(カード名・値段・出来事)が1つあると実在感が出る
- 50字前後の短い投稿を恐れない(140字近くまで埋める必要はない)
- 感情は説明せず、言い方に滲ませる

# 出力手順

まず候補を3つ書き、それぞれ自分で「AI感がないか」を上のリストで検査する。
最後に、最も人間っぽい1つを選んで以下の形式で出力:

<候補>
(候補3つと自己検査をここに)
</候補>
<投稿>
(選んだ投稿本文のみ)
</投稿>

- 文字数は40〜140字
- 直近の投稿と話題・表現・出だしの言葉が被らないこと
- ハッシュタグは0〜2個まで、絵文字は0〜2個まで
- ペルソナの口調・関心領域・職業感(性別・年代)には沿うこと
- Clove名指しは10投稿のうち3〜4回程度の頻度なので、今日言及するかはペルソナと話題に応じて判断"""


def generate_post_for_account(client, slug: str, now_jst: datetime):
    persona_path = ACCOUNTS_DIR / slug / "persona.md"
    if not persona_path.exists():
        return None, f"persona missing: {persona_path}"

    persona = read_text(persona_path)
    rules = read_text(RULES_PATH)
    examples = read_text(EXAMPLES_PATH)
    recent = get_recent_posts(slug)

    benchmark = get_benchmark_sample() or "(サンプルなし)"
    prompt = build_post_prompt(persona, rules, examples, recent, now_jst, benchmark)
    last_err = None
    for attempt in range(4):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1500,
                temperature=1.0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                b.text for b in response.content if getattr(b, "type", "") == "text"
            ).strip()
            # <投稿>タグ内の本文を採用(3案生成→自選方式)
            m = re.search(r"<投稿>\s*(.*?)\s*</投稿>", text, re.DOTALL)
            if m:
                text = m.group(1).strip()
            elif "\n---\n" in text:
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

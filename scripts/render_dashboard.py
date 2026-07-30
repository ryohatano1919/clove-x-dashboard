#!/usr/bin/env python3
"""
Render dashboard HTMLs:
  - docs/index.html       : 全カード一覧 (Hero さん用、全体把握)
  - docs/{slug}.html      : 各アカウント用個別ページ (各携帯のブックマーク用)

Each individual page includes a "login confirm" checkbox that must be checked
before the "X で投稿する" button is active. This prevents accidental
posting from the wrong account.

Usage:
    python3 scripts/render_dashboard.py             # 今日の日付
    python3 scripts/render_dashboard.py --date 2026-05-19
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
ACCOUNTS_DIR = REPO_ROOT / "accounts"
OUTPUT_POSTS_DIR = REPO_ROOT / "output" / "posts"
SHEET_CSV_PATH = REPO_ROOT / "output" / "accounts_from_sheet.csv"

JST = timezone(timedelta(hours=9))


def load_persona_summary(slug: str) -> str:
    persona_path = ACCOUNTS_DIR / slug / "persona.md"
    if not persona_path.exists():
        return ""
    content = persona_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    profile_lines = []
    capturing = False
    for line in lines:
        if line.startswith("## 基本プロフィール"):
            capturing = True
            continue
        if capturing:
            if line.startswith("## "):
                break
            stripped = line.strip()
            if stripped:
                profile_lines.append(stripped)
    return "\n".join(profile_lines[:7])


def load_handle_map() -> dict:
    """シートCSVから {slug: handle_name} を取得"""
    if not SHEET_CSV_PATH.exists():
        return {}
    with SHEET_CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {
            (row.get("slug") or "").strip(): (row.get("handle_name") or "").strip()
            for row in reader
            if (row.get("slug") or "").strip()
        }


# =========================
# 全体ダッシュボード (index.html)
# =========================

def render_card_for_index(item: dict, handle_map: dict) -> str:
    slug = item["slug"]
    text = item["text"]
    profile_raw = load_persona_summary(slug) or "(プロフィール未取得)"
    text_encoded = urllib.parse.quote(text)
    intent_url = f"https://twitter.com/intent/tweet?text={text_encoded}"
    char_count = len(text)
    handle = handle_map.get(slug, "")
    handle_display = f"@{html.escape(handle)}" if handle and not handle.startswith("@") else html.escape(handle) if handle else "(handle未設定)"

    text_html = html.escape(text).replace("\n", "<br>")
    profile_html = html.escape(profile_raw).replace("\n", "<br>")

    return f"""    <article class="card" data-slug="{html.escape(slug)}">
      <header class="card-header">
        <span class="slug">{html.escape(slug)}</span>
        <span class="handle">{handle_display}</span>
        <span class="char-count">{char_count}字</span>
      </header>
      <div class="profile">{profile_html}</div>
      <div class="post-text">{text_html}</div>
      <div class="card-actions">
        <a class="post-button" href="{intent_url}" target="_blank" rel="noopener noreferrer">
          🐦 X で投稿(現在ログイン中のアカ)
        </a>
        <a class="account-page-link" href="{html.escape(slug)}.html">
          👤 {html.escape(slug)} 専用ページへ →
        </a>
      </div>
    </article>"""


CSS_COMMON = """    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif;
      background: #f5f7fa;
      color: #1a1a2e;
      padding: 16px;
      line-height: 1.55;
      -webkit-font-smoothing: antialiased;
    }
    header.page-header { max-width: 1200px; margin: 0 auto 16px; }
    h1 { font-size: 1.4rem; margin-bottom: 4px; color: #1d9bf0; }
    .meta { font-size: 0.85rem; color: #666; }
    .card {
      background: white;
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .card-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; }
    .slug { font-weight: 700; color: #1d9bf0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.95rem; }
    .handle { font-size: 0.85rem; color: #555; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .char-count { font-size: 0.75rem; color: #888; }
    .profile {
      font-size: 0.78rem;
      color: #666;
      padding: 8px 10px;
      background: #f8f9fa;
      border-radius: 8px;
      border-left: 3px solid #1d9bf0;
    }
    .post-text {
      background: #fff8e7;
      padding: 14px;
      border-radius: 10px;
      white-space: pre-wrap;
      word-wrap: break-word;
      font-size: 0.95rem;
      border: 1px solid #f0e1b8;
      min-height: 80px;
    }
    .post-button {
      display: block;
      text-align: center;
      background: #1d9bf0;
      color: white !important;
      padding: 14px;
      border-radius: 999px;
      text-decoration: none;
      font-weight: 700;
      transition: background 0.2s, transform 0.05s;
      font-size: 0.95rem;
    }
    .post-button:hover { background: #1a8cd8; }
    .post-button:active { background: #1681c4; transform: scale(0.98); }
    .post-button.disabled {
      background: #ccc !important;
      pointer-events: none;
      cursor: not-allowed;
      opacity: 0.6;
    }
"""

CSS_INDEX = CSS_COMMON + """    .cards {
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
      max-width: 1200px;
      margin: 0 auto;
    }
    @media (min-width: 768px) { .cards { grid-template-columns: 1fr 1fr; } }
    @media (min-width: 1100px) { .cards { grid-template-columns: 1fr 1fr 1fr; } }
    .card-actions { display: flex; flex-direction: column; gap: 8px; }
    .account-page-link {
      display: block;
      text-align: center;
      background: #eef5fb;
      color: #1d9bf0 !important;
      padding: 8px;
      border-radius: 8px;
      text-decoration: none;
      font-size: 0.85rem;
      font-weight: 500;
    }
    .account-page-link:hover { background: #d8e9f5; }
"""

CSS_ACCOUNT = CSS_COMMON + """    main.single { max-width: 600px; margin: 0 auto; }
    .warning-banner {
      background: linear-gradient(135deg, #fff3cd, #ffe8a8);
      border: 2px solid #ffc107;
      padding: 18px;
      border-radius: 14px;
      margin-bottom: 14px;
      text-align: center;
    }
    .warning-banner h2 {
      font-size: 1.1rem;
      margin-bottom: 6px;
      color: #663d00;
    }
    .warning-banner strong {
      font-size: 1.3rem;
      color: #1d9bf0;
      display: block;
      margin: 4px 0;
    }
    .warning-banner p { font-size: 0.85rem; color: #663d00; }
    .login-check {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 14px;
      background: #f0f8ff;
      border: 2px solid #1d9bf0;
      border-radius: 10px;
      cursor: pointer;
      font-size: 0.9rem;
      font-weight: 600;
    }
    .login-check input[type="checkbox"] {
      width: 22px;
      height: 22px;
      flex-shrink: 0;
      margin-top: 1px;
      cursor: pointer;
    }
    .login-check.checked {
      background: #e8f5e9;
      border-color: #4caf50;
    }
    .back-link {
      display: inline-block;
      margin-top: 16px;
      color: #888;
      font-size: 0.85rem;
      text-decoration: none;
    }
    .back-link:hover { color: #1d9bf0; }
"""


def render_index_html(date_str: str, items: list[dict], handle_map: dict) -> str:
    cards_html = "\n".join(render_card_for_index(it, handle_map) for it in items)
    count = len(items)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="theme-color" content="#1d9bf0">
  <title>Clove X投稿ダッシュボード — {date_str}</title>
  <style>
{CSS_INDEX}  </style>
</head>
<body>
  <header class="page-header">
    <h1>Clove X投稿ダッシュボード(全体)</h1>
    <div class="meta">📅 {date_str} ・ {count}件 ・ 各カードから個別ページへ移動できます</div>
  </header>
  <main class="cards">
{cards_html}
  </main>
</body>
</html>
"""


# =========================
# アカウント別ページ ({slug}.html)
# =========================

def render_account_html(date_str: str, item: dict, handle: str) -> str:
    slug = item["slug"]
    text = item["text"]
    profile_raw = load_persona_summary(slug) or "(プロフィール未取得)"
    text_encoded = urllib.parse.quote(text)
    intent_url = f"https://twitter.com/intent/tweet?text={text_encoded}"
    char_count = len(text)

    handle_display = handle if handle else "(handle未設定)"
    handle_safe = html.escape(handle_display)

    text_html = html.escape(text).replace("\n", "<br>")
    profile_html = html.escape(profile_raw).replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta name="theme-color" content="#1d9bf0">
  <title>{html.escape(slug)} 専用 — {date_str}</title>
  <style>
{CSS_ACCOUNT}  </style>
</head>
<body>
  <main class="single">
    <div class="warning-banner">
      <h2>このページは ↓</h2>
      <strong>{handle_safe}</strong>
      <p>専用です。他のアカウントでログイン中の場合は投稿しないでください。</p>
    </div>

    <article class="card" data-slug="{html.escape(slug)}">
      <header class="card-header">
        <span class="slug">{html.escape(slug)}</span>
        <span class="char-count">{char_count}字</span>
      </header>
      <div class="profile">{profile_html}</div>
      <div class="post-text">{text_html}</div>

      <label class="login-check" id="login-label">
        <input type="checkbox" id="login-confirm">
        <span>👆 {handle_safe} でログイン中であることを確認しました</span>
      </label>

      <a class="post-button disabled" id="post-btn" href="{intent_url}" target="_blank" rel="noopener noreferrer">
        🐦 X で投稿する
      </a>
    </article>

    <a class="back-link" href="index.html">← 全体ダッシュボードに戻る</a>
  </main>

  <script>
    const checkbox = document.getElementById('login-confirm');
    const btn = document.getElementById('post-btn');
    const label = document.getElementById('login-label');

    checkbox.addEventListener('change', function() {{
      if (this.checked) {{
        btn.classList.remove('disabled');
        label.classList.add('checked');
      }} else {{
        btn.classList.add('disabled');
        label.classList.remove('checked');
      }}
    }});

    btn.addEventListener('click', function(e) {{
      if (!checkbox.checked) {{
        e.preventDefault();
        alert('まず "ログイン中であることを確認しました" にチェックを入れてください');
        return false;
      }}
    }});
  </script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date (YYYY-MM-DD)", default=None)
    args = parser.parse_args()

    now_jst = datetime.now(JST)
    date_str = args.date or now_jst.strftime("%Y-%m-%d")

    summary_path = OUTPUT_POSTS_DIR / f"{date_str}.json"
    if not summary_path.exists():
        print(f"ERROR: {summary_path} not found. Run generate_daily_posts.py first.", file=sys.stderr)
        return 1

    items = json.loads(summary_path.read_text(encoding="utf-8"))
    if not items:
        print("WARN: no items in summary.", file=sys.stderr)

    handle_map = load_handle_map()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # index.html (全体)
    index_html = render_index_html(date_str, items, handle_map)
    (DOCS_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print(f"Rendered: docs/index.html ({len(items)} cards)")

    # 個別ページ
    individual_count = 0
    for item in items:
        slug = item["slug"]
        handle = handle_map.get(slug, "")
        account_html = render_account_html(date_str, item, handle)
        (DOCS_DIR / f"{slug}.html").write_text(account_html, encoding="utf-8")
        individual_count += 1

    print(f"Rendered: docs/{{slug}}.html × {individual_count} individual pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())

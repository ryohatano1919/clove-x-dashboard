#!/usr/bin/env python3
"""
Generate 20 distinct Clove user personas as Markdown files under accounts/.

Environment:
    ANTHROPIC_API_KEY required.

Usage:
    python3 scripts/generate_personas.py                       # 全アカ生成(既存はスキップ)
    python3 scripts/generate_personas.py --only f20_01,m30_01  # 特定スラグだけ
    python3 scripts/generate_personas.py --overwrite           # 既存上書き
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = REPO_ROOT / "accounts"

CLAUDE_MODEL = "claude-haiku-4-5"

# アカウント定義 (slug, 年代, 性別)
ACCOUNTS = [
    # 20代女性 5人
    ("f20_01", "20代前半", "女性"),
    ("f20_02", "20代中盤", "女性"),
    ("f20_03", "20代後半", "女性"),
    ("f20_04", "20代前半", "女性"),
    ("f20_05", "20代後半", "女性"),
    # 20代男性 5人
    ("m20_01", "20代前半", "男性"),
    ("m20_02", "20代中盤", "男性"),
    ("m20_03", "20代後半", "男性"),
    ("m20_04", "20代前半", "男性"),
    ("m20_05", "20代後半", "男性"),
    # 30代男性 10人
    ("m30_01", "30代前半", "男性"),
    ("m30_02", "30代中盤", "男性"),
    ("m30_03", "30代後半", "男性"),
    ("m30_04", "30代前半", "男性"),
    ("m30_05", "30代中盤", "男性"),
    ("m30_06", "30代後半", "男性"),
    ("m30_07", "30代前半", "男性"),
    ("m30_08", "30代中盤", "男性"),
    ("m30_09", "30代後半", "男性"),
    ("m30_10", "30代前半", "男性"),
]

# 職業候補(性別×年代別)
OCCUPATIONS = {
    ("女性", "20代前半"): ["看護師", "事務職OL", "アパレル販売員", "保育士", "新人IT職", "受付", "美容部員"],
    ("女性", "20代中盤"): ["Webデザイナー", "営業職", "美容師", "フリーランスライター", "教員", "経理事務"],
    ("女性", "20代後半"): ["中堅看護師", "Webディレクター", "薬剤師", "公務員", "中堅事務職", "保健師"],
    ("男性", "20代前半"): ["大学院生", "新人SE", "営業職", "フリーター", "工場勤務", "サービス業バイト"],
    ("男性", "20代中盤"): ["SE", "営業マン", "店舗運営", "建設業", "技術職", "公務員"],
    ("男性", "20代後半"): ["中堅SE", "営業職", "公務員", "技術職", "フリーランス", "サービス業"],
    ("男性", "30代前半"): ["SE", "営業職", "公務員", "メーカー技術", "中小企業勤務", "個人事業主", "配送業"],
    ("男性", "30代中盤"): ["係長クラスSE", "営業課長候補", "中小企業役員候補", "教師", "医療職"],
    ("男性", "30代後半"): ["管理職SE", "営業課長", "工場長候補", "個人事業主", "ベテラン技術職"],
}

# ポケカ歴(復帰勢を多めに)
TCG_HISTORY = [
    "復帰勢(子供の頃以来)",
    "復帰勢(数年ぶりに最近戻ってきた)",
    "復帰勢(コロナ禍にハマり直した)",
    "新規(1年未満)",
    "新規(半年前から)",
    "ベテラン(継続的に追ってる)",
    "コレクター志向(値段より好み重視)",
]

# 関心領域
INTERESTS = [
    "バトル派(対戦が主目的)",
    "コレクション派(集めるのが好き)",
    "オリパ派(ガチャ的に楽しむ)",
    "シングル派(値段重視)",
    "投資派(控えめ・損切り上手)",
    "デザイン派(イラスト目的)",
]


def build_persona_prompt(slug, age_band, gender, occupation, tcg_history, interest, notes=""):
    notes_block = ""
    if notes and notes.strip():
        notes_block = f"\n# 追加で必ず守る制約 (Hero さん指示)\n{notes.strip()}\n"

    return f"""あなたは X(Twitter) で活動する架空のユーザーのペルソナを設計しています。
以下の固定属性を踏まえて、リアルで個性のあるペルソナを Markdown 形式で1つ作成してください。

# 固定属性
- アカウントSlug: {slug}
- 年代: {age_band}
- 性別: {gender}
- 職業: {occupation}
- ポケカ歴: {tcg_history}
- 関心領域: {interest}{notes_block}

# 共通方針
- Cloveオリパ(ポケモンカードのオンラインオリパサイト)を使っている匿名ユーザー
- 等身大の温度感(ステマ感なし、盲信せず)
- 他のペルソナと被らない個性を持つ
- Clove言及は10投稿のうち3〜4回程度に抑える前提

# 出力フォーマット (Markdown 本体のみを出力)

# {slug} ペルソナ

## 基本プロフィール
- ハンドルネーム: (X で使いそうなネット名を1つ。本名・実名を匂わせない)
- 年代/性別: {age_band} {gender}
- 職業: {occupation}
- 居住地ニュアンス: (関東/関西/地方都市など、明言しない範囲で1つ)
- 家族構成: (一人暮らし/実家/結婚/子供あり など、自然なもの1つ)
- ポケカ歴: {tcg_history}

## 一人称・口調
- 一人称: (該当する一人称を1〜2個、場面別に)
- 語尾の癖: (3〜4個の代表例)
- テンション傾向: (テンション高め/中/低、状況による解説)

## ライフスタイル・投稿傾向
- 平日の活動と投稿時間帯:
- 休日の過ごし方:
- ポケカに割く時間:

## ポケカへの関わり方
- 興味の中心: ({interest}ベース、具体的に)
- 開封スタイル:
- お気に入りカード/シリーズ: (1〜2個、なるべく具体的なカード名やシリーズ名で)

## Cloveとの関わり方
- 使い始めたきっかけ:
- お気に入りオリパタイプ:
- 言及頻度や温度感:

## 口癖・特徴的表現
- (3〜5個の口癖を箇条書き、その人独自のもの)

## NG / 言わなさそうな表現
- (このペルソナが絶対言わなさそうな表現を2〜3個)

# 重要
- リアルな個性を出す。テンプレ的にならず、生活感のある描写を入れる
- 年代・性別・職業に合った自然な口調にする
- 「自分」「俺」「私」「ウチ」など一人称も年代・性別に合わせる
- 上記 Markdown フォーマットを正確に守る
- 出力は Markdown 本体のみ。前置き・後置き・コードフェンス(```)は一切不要

それでは {slug} のペルソナを生成してください:
"""


def clean_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```markdown"):
        text = text[len("```markdown"):].strip()
    elif text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def generate_persona(client, slug, age_band, gender, occupation, tcg_history, interest, notes="", max_retries=4):
    prompt = build_persona_prompt(slug, age_band, gender, occupation, tcg_history, interest, notes)
    last_err = None
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            return clean_markdown(response.content[0].text)
        except (anthropic.APIStatusError, anthropic.RateLimitError, anthropic.APIConnectionError) as e:
            last_err = e
            wait = 2 ** attempt + random.random()
            print(f"  [retry {attempt+1}/{max_retries}] {type(e).__name__}: sleeping {wait:.1f}s", flush=True)
            time.sleep(wait)
    raise last_err  # type: ignore[misc]


def load_attrs_from_file(path: Path) -> dict:
    """CSV/TSV ファイルから属性を読み込む。各行は slug,age_band,gender,occupation,tcg_history,interest,notes"""
    if not path.exists():
        raise FileNotFoundError(f"attrs file not found: {path}")
    text = path.read_text(encoding="utf-8")
    delim = "\t" if "\t" in text.split("\n", 1)[0] else ","
    reader = csv.DictReader(text.splitlines(), delimiter=delim)
    result = {}
    for row in reader:
        slug = (row.get("slug") or "").strip()
        if not slug:
            continue
        result[slug] = {
            "age_band": (row.get("age_band") or "").strip(),
            "gender": (row.get("gender") or "").strip(),
            "occupation": (row.get("occupation") or "").strip(),
            "tcg_history": (row.get("tcg_history") or "").strip(),
            "interest": (row.get("interest") or "").strip(),
            "notes": (row.get("notes") or "").strip(),
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Generate only these slugs (comma-separated)", default=None)
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing personas")
    parser.add_argument("--attrs-file", help="Path to CSV/TSV with attributes (overrides built-in defaults)", default=None)
    args = parser.parse_args()

    client = anthropic.Anthropic()
    target_slugs = set(args.only.split(",")) if args.only else None

    # 属性マップ構築:
    #   --attrs-file 指定があれば、それを最優先
    #   なければ、内蔵リストとランダム割当を使う(再現性のため seed 42)
    if args.attrs_file:
        attrs_path = Path(args.attrs_file)
        if not attrs_path.is_absolute():
            attrs_path = REPO_ROOT / attrs_path
        attr_map = load_attrs_from_file(attrs_path)
        # account 順序はファイル順を尊重
        ordered_slugs = list(attr_map.keys())
        print(f"[CONFIG] attrs from: {attrs_path.relative_to(REPO_ROOT)} ({len(attr_map)} accounts)", file=sys.stderr)
    else:
        random.seed(42)
        attr_map = {}
        for slug, age_band, gender in ACCOUNTS:
            occ_list = OCCUPATIONS[(gender, age_band)]
            attr_map[slug] = {
                "age_band": age_band,
                "gender": gender,
                "occupation": random.choice(occ_list),
                "tcg_history": random.choice(TCG_HISTORY),
                "interest": random.choice(INTERESTS),
                "notes": "",
            }
        ordered_slugs = [s for s, _, _ in ACCOUNTS]

    for slug in ordered_slugs:
        if target_slugs and slug not in target_slugs:
            continue

        out_dir = ACCOUNTS_DIR / slug
        persona_path = out_dir / "persona.md"

        if persona_path.exists() and not args.overwrite:
            print(f"[SKIP] {slug} (already exists)")
            continue

        a = attr_map[slug]
        notes_hint = f" / notes='{a.get('notes', '')[:30]}...'" if a.get("notes") else ""
        print(f"[GEN] {slug}: {a['age_band']}{a['gender']} / {a['occupation']} / {a['tcg_history']} / {a['interest']}{notes_hint}")

        try:
            persona = generate_persona(
                client, slug, a["age_band"], a["gender"],
                a["occupation"], a["tcg_history"], a["interest"],
                notes=a.get("notes", ""),
            )
        except Exception as e:
            print(f"[ERROR] {slug}: {e}", file=sys.stderr)
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "posts").mkdir(parents=True, exist_ok=True)
        persona_path.write_text(persona, encoding="utf-8")
        print(f"[OK] {slug} -> {persona_path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

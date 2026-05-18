#!/usr/bin/env python3
"""
Dump current 20 accounts' attributes as TSV (for pasting into Google Sheets).

Usage:
    python3 scripts/dump_attrs.py           # 標準出力にTSV
    python3 scripts/dump_attrs.py --out output/accounts.tsv  # ファイルへ
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = REPO_ROOT / "accounts"

# generate_personas.py と同じリスト(再現性のため seed 42 固定)
ACCOUNTS = [
    ("f20_01", "20代前半", "女性"),
    ("f20_02", "20代中盤", "女性"),
    ("f20_03", "20代後半", "女性"),
    ("f20_04", "20代前半", "女性"),
    ("f20_05", "20代後半", "女性"),
    ("m20_01", "20代前半", "男性"),
    ("m20_02", "20代中盤", "男性"),
    ("m20_03", "20代後半", "男性"),
    ("m20_04", "20代前半", "男性"),
    ("m20_05", "20代後半", "男性"),
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

TCG_HISTORY = [
    "復帰勢(子供の頃以来)",
    "復帰勢(数年ぶりに最近戻ってきた)",
    "復帰勢(コロナ禍にハマり直した)",
    "新規(1年未満)",
    "新規(半年前から)",
    "ベテラン(継続的に追ってる)",
    "コレクター志向(値段より好み重視)",
]

INTERESTS = [
    "バトル派(対戦が主目的)",
    "コレクション派(集めるのが好き)",
    "オリパ派(ガチャ的に楽しむ)",
    "シングル派(値段重視)",
    "投資派(控えめ・損切り上手)",
    "デザイン派(イラスト目的)",
]


def extract_handle(slug: str) -> str:
    persona_path = ACCOUNTS_DIR / slug / "persona.md"
    if not persona_path.exists():
        return ""
    content = persona_path.read_text(encoding="utf-8")
    m = re.search(r"ハンドルネーム[::]\s*(.+?)$", content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""


def build_attr_map():
    """generate_personas.py と同じロジックで属性を割当"""
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
        }
    return attr_map


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="Output file path (default: stdout)", default=None)
    args = parser.parse_args()

    attr_map = build_attr_map()

    lines = []
    lines.append("\t".join([
        "slug", "age_band", "gender", "occupation",
        "tcg_history", "interest", "handle_name", "notes"
    ]))

    for slug, age_band, gender in ACCOUNTS:
        a = attr_map[slug]
        handle = extract_handle(slug)
        lines.append("\t".join([
            slug, a["age_band"], a["gender"], a["occupation"],
            a["tcg_history"], a["interest"], handle, ""
        ]))

    output = "\n".join(lines) + "\n"

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = REPO_ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Wrote: {out_path.relative_to(REPO_ROOT)}", file=sys.stderr)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    sys.exit(main() or 0)

#!/usr/bin/env python3
"""
Sync persona attributes from Google Sheets and regenerate changed personas.

Workflow:
  1. Fetch CSV from Google Sheets (env: SHEET_ID)
  2. Compare with last snapshot in output/accounts_snapshot.tsv
  3. Detect changed/added accounts
  4. Regenerate persona.md for changed accounts (generate_personas.py)
  5. Regenerate today's post for changed accounts (generate_daily_posts.py)
  6. Re-render dashboard (render_dashboard.py)
  7. Update snapshot

Environment:
    SHEET_ID            Google Sheets ID (required)
    ANTHROPIC_API_KEY   Required for regeneration

Usage:
    python3 scripts/sync_from_sheets.py              # Diff + regenerate
    python3 scripts/sync_from_sheets.py --dry-run    # Diff only
    python3 scripts/sync_from_sheets.py --force-all  # Force regenerate all
    python3 scripts/sync_from_sheets.py --only f20_01,m30_01  # Specific slugs only
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
CACHED_CSV_PATH = OUTPUT_DIR / "accounts_from_sheet.csv"
SNAPSHOT_PATH = OUTPUT_DIR / "accounts_snapshot.tsv"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# 比較対象の属性(handle_name は AI 生成なので除外)
COMPARE_ATTRS = ["age_band", "gender", "occupation", "tcg_history", "interest", "notes"]


def fetch_sheet_csv(sheet_id: str) -> str:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_csv(csv_text: str) -> dict:
    """{slug: {attr: value}}"""
    reader = csv.DictReader(io.StringIO(csv_text))
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
            "handle_name": (row.get("handle_name") or "").strip(),
        }
    return result


def load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        return {}
    text = SNAPSHOT_PATH.read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    result = {}
    for row in reader:
        slug = (row.get("slug") or "").strip()
        if slug:
            result[slug] = {a: (row.get(a) or "").strip() for a in COMPARE_ATTRS}
    return result


def save_snapshot(current: dict):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cols = ["slug"] + COMPARE_ATTRS
    with SNAPSHOT_PATH.open("w", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for slug, a in current.items():
            row = [slug] + [a.get(c, "") for c in COMPARE_ATTRS]
            f.write("\t".join(row) + "\n")


def detect_changes(current: dict, snapshot: dict):
    """returns (added, changed, removed)"""
    added = [s for s in current if s not in snapshot]
    removed = [s for s in snapshot if s not in current]
    changed = []
    for slug in current:
        if slug not in snapshot:
            continue
        for a in COMPARE_ATTRS:
            if current[slug].get(a, "") != snapshot[slug].get(a, ""):
                changed.append(slug)
                break
    return added, changed, removed


def run_subscript(cmd_list, label):
    print(f"\n>>> {label}", flush=True)
    print(f"    $ {' '.join(cmd_list)}", flush=True)
    result = subprocess.run(cmd_list, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"!!! {label} failed (exit {result.returncode})", file=sys.stderr)
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Just detect changes, don't regenerate")
    parser.add_argument("--force-all", action="store_true", help="Regenerate all accounts in sheet")
    parser.add_argument("--only", help="Regenerate only these slugs", default=None)
    parser.add_argument("--skip-posts", action="store_true", help="Don't regenerate today's posts")
    parser.add_argument("--skip-dashboard", action="store_true", help="Don't re-render dashboard")
    parser.add_argument("--init", action="store_true", help="Initialize snapshot from current sheet without regenerating")
    args = parser.parse_args()

    sheet_id = os.environ.get("SHEET_ID")
    if not sheet_id:
        print("ERROR: SHEET_ID env var required (add to .env)", file=sys.stderr)
        return 1

    print(f"[1/6] Fetching sheet: {sheet_id}", flush=True)
    try:
        csv_text = fetch_sheet_csv(sheet_id)
    except Exception as e:
        print(f"ERROR fetching sheet: {e}", file=sys.stderr)
        return 1

    # ローカルキャッシュ保存
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHED_CSV_PATH.write_text(csv_text, encoding="utf-8")
    print(f"      cached: {CACHED_CSV_PATH.relative_to(REPO_ROOT)}", flush=True)

    current = parse_csv(csv_text)
    print(f"      -> {len(current)} accounts in sheet", flush=True)

    if args.init:
        save_snapshot(current)
        print(f"\n[init] snapshot saved without regenerating: {SNAPSHOT_PATH.relative_to(REPO_ROOT)}", flush=True)
        print(f"       Next sync will detect changes against this baseline.", flush=True)
        return 0

    print(f"\n[2/6] Comparing with snapshot...", flush=True)
    snapshot = load_snapshot()
    added, changed, removed = detect_changes(current, snapshot)

    if not snapshot:
        print(f"      No previous snapshot. All accounts considered NEW.", flush=True)
    print(f"      ADDED   ({len(added)}): {', '.join(added) if added else '(none)'}", flush=True)
    print(f"      CHANGED ({len(changed)}): {', '.join(changed) if changed else '(none)'}", flush=True)
    if removed:
        print(f"      REMOVED ({len(removed)}): {', '.join(removed)} (kept on disk)", flush=True)

    # 再生成対象決定
    if args.force_all:
        targets = sorted(current.keys())
        print(f"\n[3/6] --force-all -> targeting ALL {len(targets)} accounts", flush=True)
    elif args.only:
        only_set = set(args.only.split(","))
        targets = sorted(s for s in current if s in only_set)
        print(f"\n[3/6] --only -> targeting {len(targets)} accounts: {', '.join(targets)}", flush=True)
    else:
        targets = sorted(set(added + changed))
        print(f"\n[3/6] Diff -> targeting {len(targets)} accounts: {', '.join(targets) if targets else '(none)'}", flush=True)

    if not targets:
        # 属性変更なし: ペルソナ・投稿は触らないが、handle_name や軽微変更を反映するため
        # ダッシュボードだけは再描画する。
        if not args.skip_dashboard:
            run_subscript(
                ["python3", str(SCRIPTS_DIR / "render_dashboard.py")],
                "[render only] handle_name 等を HTML に反映"
            )
        print(f"\nNo persona/post regeneration. Snapshot updated.", flush=True)
        save_snapshot(current)
        return 0

    if args.dry_run:
        print(f"\n--dry-run: stopping. Run without --dry-run to apply.", flush=True)
        return 0

    # ---- 再生成 ----
    only_str = ",".join(targets)

    ok = run_subscript(
        ["python3", str(SCRIPTS_DIR / "generate_personas.py"),
         "--attrs-file", str(CACHED_CSV_PATH.relative_to(REPO_ROOT)),
         "--only", only_str,
         "--overwrite"],
        f"[4/6] Regenerating {len(targets)} personas"
    )
    if not ok:
        return 2

    if not args.skip_posts:
        ok = run_subscript(
            ["python3", str(SCRIPTS_DIR / "generate_daily_posts.py"),
             "--only", only_str,
             "--overwrite"],
            f"[5/6] Regenerating today's posts for {len(targets)} accounts"
        )
        if not ok:
            return 3
        # サマリを全アカ分に復元(--only バグ対応)
        run_subscript(
            ["python3", str(SCRIPTS_DIR / "generate_daily_posts.py")],
            "[5/6] Refresh full summary JSON"
        )
    else:
        print(f"\n[5/6] --skip-posts: skipped", flush=True)

    if not args.skip_dashboard:
        ok = run_subscript(
            ["python3", str(SCRIPTS_DIR / "render_dashboard.py")],
            "[6/6] Re-rendering dashboard"
        )
        if not ok:
            return 4
    else:
        print(f"\n[6/6] --skip-dashboard: skipped", flush=True)

    # スナップショット更新
    save_snapshot(current)
    print(f"\n[done] snapshot updated: {SNAPSHOT_PATH.relative_to(REPO_ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

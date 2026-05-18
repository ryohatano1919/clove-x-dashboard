# Clove X自動投稿Bot セットアップ手順

別PCで動かすための最小セットアップ手順書。

---

## 必要なもの

- Python 3.9 以上
- APIキー5つ（メモ済みのもの）
  - `ANTHROPIC_API_KEY`
  - `X_API_KEY`
  - `X_API_SECRET`
  - `X_ACCESS_TOKEN`
  - `X_ACCESS_TOKEN_SECRET`

---

## セットアップ手順

### 1. このフォルダ（x-bot/）を任意の場所に置く

例: デスクトップに置く

### 2. Python 依存ライブラリをインストール

ターミナルで x-bot フォルダに移動して:

```bash
cd ~/Desktop/x-bot
pip3 install --user -r scripts/requirements.txt
```

### 3. .env ファイルを作成

`scripts/.env.example` をプロジェクトルート（`x-bot/` 直下）に `.env` という名前でコピーして編集:

```bash
cp scripts/.env.example .env
nano .env
```

`nano` が開いたら、各行の `=` の直後にキーを貼り付け:

```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxx...
X_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxx
X_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
X_ACCESS_TOKEN=xxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
X_ACCESS_TOKEN_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

保存: `Ctrl+O` → `Enter` → `Ctrl+X`

⚠️ 注意点:
- `=` の前後にスペース入れない
- 値をクオート（"`'`）で囲まない
- 改行入れない（全部1行で）

---

## 動作テスト

### ドライラン（投稿せず生成だけ）

```bash
cd ~/Desktop/x-bot
set -a && source .env && set +a
python3 scripts/post_to_x.py --dry-run
```

→ 生成された投稿文がターミナルに表示される（実投稿はしない）

### 実投稿テスト（1件投稿される）

```bash
cd ~/Desktop/x-bot
set -a && source .env && set +a
python3 scripts/post_to_x.py
```

→ 1件投稿される + `output/content/x-post-log.md` に履歴追加される

---

## ファイル構成

```
x-bot/
├── SETUP.md                          # このファイル
├── .env                              # APIキー（自分で作成、Git絶対不可）
├── scripts/
│   ├── post_to_x.py                  # メインスクリプト
│   ├── requirements.txt              # Python依存
│   └── .env.example                  # .env のひな形
├── reference/
│   ├── x-user-persona.md             # ペルソナ定義（運用しながら育てる）
│   ├── x-post-examples.md            # 投稿お手本
│   └── x-post-rules.md               # 投稿ルール
└── output/
    └── content/
        └── x-post-log.md             # 投稿履歴（自動更新）
```

---

## 育てるファイル

運用しながら手を入れる主なファイル:

- `reference/x-user-persona.md` — ペルソナ細かい性格付け、口癖追加
- `reference/x-post-examples.md` — 反応が良かった投稿を「お手本」として追加
- `reference/x-post-rules.md` — NG表現発見時に追記
- `output/content/x-post-log.md` — 自動更新（手動編集不要）

---

## GitHub Actions による自動化（オプション）

1時間ごとの自動投稿はGitHub Actionsで実現します。
セットアップ手順は別途案内が必要なら問い合わせてください。

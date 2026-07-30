# 投稿候補スプシ連携のセットアップ（1回だけ）

生成された投稿候補（1アカウント×3タイプ）を自動でスプレッドシートに書き込むための設定。

## 1. スプレッドシートを用意

新しいスプシを作り、1行目にヘッダーを入れる：

| 日付 | アカウント | タイプ | 投稿文 | 使った？ |
|---|---|---|---|---|

## 2. Apps Script を設定

スプシの「拡張機能 → Apps Script」を開き、以下を貼り付けて保存：

```javascript
function doPost(e) {
  const data = JSON.parse(e.postData.contents);
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];

  // 同じ日付の行が既にあれば削除（再実行時の重複防止）
  const values = sheet.getDataRange().getValues();
  for (let i = values.length - 1; i >= 1; i--) {
    if (values[i][0] === data.date) sheet.deleteRow(i + 1);
  }

  data.rows.forEach(row => sheet.appendRow(row));
  return ContentService.createTextOutput(
    JSON.stringify({ok: true, added: data.rows.length})
  ).setMimeType(ContentService.MimeType.JSON);
}
```

## 3. Webアプリとしてデプロイ

1. 右上「デプロイ → 新しいデプロイ」
2. 種類：「ウェブアプリ」
3. 次のユーザーとして実行：**自分**
4. アクセスできるユーザー：**全員**
5. デプロイ → 表示された **ウェブアプリURL** をコピー

## 4. GitHub Secretsに登録

リポジトリの Settings → Secrets and variables → Actions → New repository secret

- Name: `SHEET_WEBHOOK_URL`
- Secret: コピーしたウェブアプリURL（**改行や空白が入らないよう注意**）

以上。次の自動実行から、毎回そのスプシに候補が書き込まれる（同日の再実行は上書き）。

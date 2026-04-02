# credential-vault CLI利用イメージ

このドキュメントは、実装前の CLI 体験を具体化するためのモックです。
まだ実行可能なコマンドではなく、「実際に使うとこう見える」を先に固める目的で書いています。

2026-04-02 時点の実装はまだ `unlock` セッション未対応で、当面は direct-password モードです。
対話プロンプトか `CREDENTIAL_VAULT_MASTER_PASSWORD` 環境変数で vault を開く前提になっています。

## 1. どんな場面で使うか

### 1.1 人間が使う場面

- 新しい API キーを登録する
- 既存のキー一覧を確認する
- 値そのものを確認する
- 古い値を更新する

### 1.2 プロジェクトが使う場面

- バッチ処理の起動時に必要なトークンを取得する
- `.env` に置かず、その場で秘密値を受け取る
- vault がロック中なら明示的に失敗する

## 2. 最終形の体験イメージ

最終形では、最初に `unlock` しておくと、その後の `get/set/list/view` は軽快に使える想定です。

### 2.1 初回セットアップ

```bash
$ secrets init
Vault path: /home/horizontalhold/auto_project/credential-vault/vault.enc
Master password: ********
Confirm password: ********
Vault initialized.

$ secrets status
Vault: locked
Path: /home/horizontalhold/auto_project/credential-vault/vault.enc
Session: none
```

### 2.2 作業開始時にアンロック

```bash
$ secrets unlock --ttl 8h
Master password: ********
Vault unlocked.
Session expires at: 2026-04-02 18:00:00 JST

$ secrets status
Vault: unlocked
Path: /home/horizontalhold/auto_project/credential-vault/vault.enc
Session: active
TTL: 7h 59m
```

### 2.3 新しいキーを登録する

値を引数に直接書かず、対話入力か標準入力を使うのが基本です。

```bash
$ secrets set NOTION_TOKEN --classification P1b --description "Notion API token" --tag notion --tag infra
Value for NOTION_TOKEN: ********
Saved: NOTION_TOKEN
```

標準入力も使えます。

```bash
$ printf '%s' "$NEW_TOKEN" | secrets set NOTION_TOKEN --stdin --classification P1b
Saved: NOTION_TOKEN
```

### 2.4 一覧を見る

```bash
$ secrets list
RECORD_ID      SERVICE       ENTITY  ACCOUNT_LABEL  CLASSIFICATION  UPDATED_AT
rec_api_001    notion        C02     本番API        P1b             2026-04-02 10:15
rec_web_001    freee-admin   C02     経理管理者     P2b             2026-04-02 10:17
rec_web_002    freee-admin   C02     閲覧専用       P2b             2026-04-02 10:18
```

値はここでは表示しません。

絞り込みもできます。

```bash
$ secrets list --classification P1b
RECORD_ID      SERVICE  ENTITY  ACCOUNT_LABEL  CLASSIFICATION  UPDATED_AT
rec_api_001    notion   C02     本番API        P1b             2026-04-02 10:15
```

サービス単位で見ると、同じサービスに複数アカウントがあることを認識できる想定です。

```bash
$ secrets list --service freee-admin
RECORD_ID      SERVICE       ENTITY  ACCOUNT_LABEL  CLASSIFICATION  UPDATED_AT
rec_web_001    freee-admin   C02     経理管理者     P2b             2026-04-02 10:17
rec_web_002    freee-admin   C02     閲覧専用       P2b             2026-04-02 10:18
```

### 2.5 値を確認する

```bash
$ secrets view rec_web_001
Record ID: rec_web_001
Service: freee-admin
Entity: C02
Account label: 経理管理者
Classification: P2b
Description: freee 管理者ログイン
Tags: freee, accounting
Login URL: https://accounts.secure.freee.co.jp/
Company code: C02
User code: admin@example.com
Password: ********
Created at: 2026-04-02 10:15
Updated at: 2026-04-02 10:15
```

必要なときだけ明示的に再表示する想定です。

```bash
$ secrets view rec_web_001 --reveal-password
Password: correct-horse-battery-staple
```

### 2.6 値だけをスクリプト向けに取得する

```bash
$ secrets get rec_api_001
secret_xxxxxxxxxxxx
```

Web ログインの特定フィールドだけを取ることもできます。

```bash
$ secrets get rec_web_001 --field username
admin@example.com

$ secrets get rec_web_001 --field password
correct-horse-battery-staple
```

このコマンドは標準出力に値だけを返すので、シェルでそのまま使えます。

```bash
$ export NOTION_TOKEN="$(secrets get rec_api_001)"
$ python src/main.py
```

### 2.7 更新する

```bash
$ secrets set NOTION_TOKEN --classification P1b --description "Notion API token"
Value for NOTION_TOKEN: ********
Updated: NOTION_TOKEN
```

### 2.8 作業終了時にロックする

```bash
$ secrets lock
Vault locked.
Session cleared.
```

## 3. 自動処理から見た体験

### 3.1 Python スクリプトの前で使う

```bash
$ NOTION_TOKEN="$(secrets get rec_api_001)" .venv/bin/python src/main.py
```

### 3.2 Bash スクリプトで安全に受ける

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! notion_token="$(secrets get rec_api_001)"; then
  echo "NOTION_TOKEN を取得できませんでした" >&2
  exit 1
fi

NOTION_TOKEN="$notion_token" .venv/bin/python src/main.py
```

### 3.3 ロック中なら明示的に失敗する

```bash
$ secrets get rec_api_001
vault is locked. run "secrets unlock" first.

$ echo $?
20
```

「値がない」のではなく「ロック中」を終了コードで判別できるようにします。

## 4. Phase 1 の暫定体験

Phase 1 ではまだ `unlock` セッションを実装しない可能性があります。
その場合、体験は少しだけ変わります。

### 4.1 `set` / `list` / `view`

対話端末なら、その場でマスターパスワードを聞いて実行します。

```bash
$ secrets list --service freee-admin
Master password: ********
RECORD_ID      SERVICE       ENTITY  ACCOUNT_LABEL  CLASSIFICATION  UPDATED_AT
rec_web_001    freee-admin   C02     経理管理者     P2b             2026-04-02 10:17
rec_web_002    freee-admin   C02     閲覧専用       P2b             2026-04-02 10:18
```

### 4.2 `get`

`get` は自動処理で使う前提が強いので、ロック状態では入力待ちせず即失敗にします。

```bash
$ secrets get rec_api_001
vault is locked.

$ echo $?
20
```

この挙動なら、バッチがパスワード待ちで止まり続ける事故を避けられます。

### 4.3 設定テンプレートを展開して別プロジェクトへ渡す

`mail-invoice-processor` のように YAML 設定を読むプロジェクトへは、テンプレート展開が使えます。

```yaml
portal_accounts:
  FUJIFILM_BI_DIRECT:
    username: "secret://rec_web_001#username"
    password: "secret://rec_web_001#password"
```

```bash
$ secrets render /path/to/local.runtime.template.yaml --output /tmp/local.runtime.generated.yaml
Rendered: /tmp/local.runtime.generated.yaml
```

実行後に消したい場合は `exec` を使います。

```bash
$ secrets exec --template /path/to/local.runtime.template.yaml -- \
  python -m bill_one_mail_ingest.url_downloader \
  --runtime-config __CREDENTIAL_VAULT_RENDERED_TEMPLATE__
```

この方法なら、別リポジトリ側のコードをすぐ大きく変えずに、平文の固定設定を減らせます。

## 5. エラー時の見え方

### 5.1 キーが存在しない

```bash
$ secrets get OPENAI_TOKEN
key not found: OPENAI_TOKEN

$ echo $?
21
```

### 5.2 vault が壊れている

```bash
$ secrets list
vault file is corrupted or cannot be decrypted.
run "secrets doctor" for details.

$ echo $?
30
```

### 5.3 権限が弱い

```bash
$ secrets doctor
[WARN] vault file permissions are too broad: 0644
[OK]   vault file exists
[OK]   encryption metadata is readable

Suggested fix:
  chmod 600 /home/horizontalhold/auto_project/credential-vault/vault.enc
```

## 6. よくある使い方

### 6.1 Notion 用のトークンを登録して使う

```bash
$ secrets unlock --ttl 8h
$ secrets set NOTION_TOKEN --classification P1b --description "Notion integration token" --tag notion
$ export NOTION_TOKEN="$(secrets get rec_api_001)"
$ python sync_notion.py
$ secrets lock
```

### 6.2 freee 用のトークンだけ一覧から探す

```bash
$ secrets list --service freee-admin
RECORD_ID      SERVICE       ENTITY  ACCOUNT_LABEL  CLASSIFICATION  UPDATED_AT
rec_web_001    freee-admin   C02     経理管理者     P2b             2026-04-02 10:17
rec_web_002    freee-admin   C02     閲覧専用       P2b             2026-04-02 10:18
```

### 6.3 値を見ずに存在だけ確認したい

```bash
$ secrets list --service freee-admin | grep 閲覧専用
rec_web_002   freee-admin   C02   閲覧専用   P2b   2026-04-02 10:18
```

## 7. 使い勝手のポイント

- 日常運用では `unlock` を 1 回すれば、その後の操作は軽い
- スクリプト向けの `get` は値だけを返すので扱いやすい
- `list` と `view` の役割を分け、一覧で値が漏れないようにする
- ロック中と未登録を終了コードで分け、自動処理が分岐しやすい
- Phase 1 から最低限使い始められ、Phase 2 で快適さを上げられる

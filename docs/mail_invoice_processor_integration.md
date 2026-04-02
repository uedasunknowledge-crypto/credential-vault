# mail-invoice-processor 連携ガイド

このガイドは、`mail-invoice-processor` が `config/local.runtime.yaml` に平文の ID/パスワードを書かなくても動けるようにするための最短ルートです。

## 1. 方針

`mail-invoice-processor` のコードをすぐ大きく変えずに進めるため、まずは次の方式を使います。

1. `mail-invoice-processor` 側にはテンプレート YAML を置く
2. 秘密値は `credential-vault` に登録する
3. 実行直前に `secrets render` または `secrets exec` で一時 YAML を展開する
4. 実アプリはその一時 YAML を `--runtime-config` で読む

## 2. テンプレートの書き方

テンプレート YAML では、秘密値を次の形式で参照します。

```text
secret://<record_ref>#<field>
```

例:

```yaml
mailbox:
  host: "secret://rec_mbx_001#host"
  username: "secret://rec_mbx_001#username"
  password: "secret://rec_mbx_001#password"
  port: "secret://rec_mbx_001#port"
  use_ssl: "secret://rec_mbx_001#use_ssl"

smtp:
  host: "secret://rec_smtp_001#host"
  username: "secret://rec_smtp_001#username"
  password: "secret://rec_smtp_001#password"
  from_address: "secret://rec_smtp_001#from_address"
  port: "secret://rec_smtp_001#port"
  use_ssl: "secret://rec_smtp_001#use_ssl"
  starttls: "secret://rec_smtp_001#starttls"

portal_accounts:
  FUJIFILM_BI_DIRECT:
    username: "secret://rec_web_001#username"
    password: "secret://rec_web_001#password"
    browser: "edge"
    headless: true
    timeout_seconds: 60
    download_timeout_seconds: 60
```

実際の叩き台としては [mail_invoice_processor.local.runtime.template.yaml](/C:/Users/kouhe/credential-vault/docs/examples/mail_invoice_processor.local.runtime.template.yaml) をそのまま使えます。

## 2.1 requirements spec も 1 枚置く

template だけだと「何が不足しているか」「人間にどの項目を入力してもらうか」が弱いため、実運用では requirements spec も置きます。

example:

- [mail_invoice_processor.requirements.example.yaml](/C:/Users/kouhe/credential-vault/docs/examples/mail_invoice_processor.requirements.example.yaml)

推奨配置:

- `mail-invoice-processor/config/local.runtime.template.yaml`
- `mail-invoice-processor/config/local.runtime.requirements.yaml`

wrapper は `local.runtime.requirements.yaml` があれば、実行前に `secrets ensure --spec ...` を自動実行します。
このとき、既存レコードが別 alias で見つかった場合は、`MAILBOX_PRIMARY` のような新しい `record_ref` alias も自動付与されます。

## 3. 最短の実行方法

### 3.1 まず一時ファイルを生成する

```powershell
.\scripts\render_mail_invoice_processor_runtime.ps1
```

### 3.2 それを使って起動する

```powershell
& C:\Users\kouhe\credential-vault\.venv\Scripts\python.exe `
  -m bill_one_mail_ingest.url_downloader `
  --runtime-config C:\Users\kouhe\mail-invoice-processor\runtime\local.runtime.generated.yaml
```

## 4. もっと安全な実行方法

`secrets exec` を使うと、一時ファイルを作って実行後に削除できます。

```powershell
.\scripts\run_mail_invoice_processor_with_vault.ps1 -Module url_downloader --max-items 10
```

このとき `__CREDENTIAL_VAULT_RENDERED_TEMPLATE__` は一時 YAML の実パスに置き換えられます。
同じ値は環境変数 `CREDENTIAL_VAULT_RENDERED_TEMPLATE` にも入ります。

`local.runtime.requirements.yaml` が存在し、不足 credential がある場合は localhost の入力フォーム URL が表示されます。人間がそこへ入力すると vault に保存され、その後の実行へ進めます。

このラッパーは次を自動で行います。

1. `mail-invoice-processor/src` を `PYTHONPATH` に追加する
2. `credential-vault/.venv/Scripts/python.exe` を既定 Python として使う
3. template を一時展開して `--runtime-config` に差し込む

現状サポートする module は次です。

- `main`
- `url_downloader`
- `delivery_sender`
- `replay_eml`

例:

```powershell
.\scripts\run_mail_invoice_processor_with_vault.ps1 -Module main --max-messages 10 --date 2026-03-31
.\scripts\run_mail_invoice_processor_with_vault.ps1 -Module delivery_sender --max-items 10
.\scripts\run_mail_invoice_processor_with_vault.ps1 -Module replay_eml data\samples\np_sample.eml --date 2026-03-31
```

`run_vpass_to_drive.py` と `run_vpass_schedule.py` は現時点では `config/local.runtime.yaml` を固定参照しているため、このラッパーの対象外です。そこは `mail-invoice-processor` 側で小さく引数対応を入れる次段で対応します。

## 5. 推奨レコードの分け方

### 5.1 メール受信系

- POP3 / IMAP の server, account, password

これらは `mailbox_account` として登録します。

### 5.2 メール送信系

- SMTP の server, account, password
- from_address

これらは `smtp_account` として登録します。

### 5.3 API パスワード系

- 各種 API キー

これらは `api_secret` として登録します。

### 5.4 サイトログイン系

- 富士フイルム BI ダイレクト
- 佐川スマートクラブ
- Vpass

これらは `web_login` として登録します。

## 6. 使うフィールド例

### 6.1 `mailbox_account`

- `host`
- `port`
- `protocol`
- `username`
- `password`
- `use_ssl`

### 6.2 `smtp_account`

- `host`
- `port`
- `username`
- `password`
- `from_address`
- `use_ssl`
- `starttls`

### 6.3 `api_secret`

- `value`
- `secret_value`
- `service_name`

### 6.4 `web_login`

- `username`
- `password`
- `login_url`
- `company_code`
- `user_code`
- `account_label`

## 7. まず登録したいもの

`mail-invoice-processor` 向けに、最低でも次を vault 化すると効果が大きいです。

1. POP3 の `mailbox.password`
2. SMTP の `smtp.password`
3. `portal_accounts` 配下の各サービスの `username` / `password`

ただし新規登録時は、`mailbox.password` や `smtp.password` だけでなく、server や account も 1 レコードへまとめて入れる方が運用しやすいです。

## 8. 次の移行ステップ

最初はテンプレート展開で十分です。
その後、余裕ができたら `mail-invoice-processor` 自体が `credential_record_id` を直接読めるように寄せると、テンプレートファイルも減らせます。

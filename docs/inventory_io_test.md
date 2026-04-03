# inventory 入出力テスト

この文書は、`docs/working/*.csv` を使って localhost 入力フォームと `secrets render` の両方を試すための手順です。

## 1. 目的

- 人間が `docs/overrides/*.csv` に非秘密メタデータを入れる
- `credential-vault` が入力用 requirements と出力確認用 template を生成する
- localhost フォームで秘密値を入れる
- vault から render して、入出力の線が通っているか確認する

## 2. 使うファイル

- [mail_invoice_credential_inventory_working.csv](/C:/Users/kouhe/credential-vault/docs/working/mail_invoice_credential_inventory_working.csv)
- [mail_invoice_auth_step_inventory_working.csv](/C:/Users/kouhe/credential-vault/docs/working/mail_invoice_auth_step_inventory_working.csv)
- [mail_invoice_io.requirements.yaml](/C:/Users/kouhe/credential-vault/docs/generated/mail_invoice_io.requirements.yaml)
- [mail_invoice_io.template.yaml](/C:/Users/kouhe/credential-vault/docs/generated/mail_invoice_io.template.yaml)
- [mail_invoice_io.summary.yaml](/C:/Users/kouhe/credential-vault/docs/generated/mail_invoice_io.summary.yaml)

## 3. 事前に埋める列

最低でも `fill_priority = P1` の行について、次を優先します。

- `source_type`
- `source_locator`
- `entity_id`
- `owner`
- `host`
- `from_address`
- `use_ssl`
- `starttls`
- `auth_flow`
- `otp_owner`

`MAILBOX_PRIMARY` は POP/IMAP の `host`、`port`、`protocol`、`username`、`use_ssl` が揃うとフォームで `password` だけ入れやすくなります。  
`SMTP_PRIMARY` は `host`、`port`、`username`、`from_address`、`use_ssl`、`starttls` を埋めると同様です。  
`VISA_VPASS` は `login_url` と `username` を working 側で確定し、フォームでは `password` と `auth_flow`、必要なら `otp_owner` を入れる形にできます。

## 4. 生成コマンド

```powershell
.\.venv\Scripts\python.exe scripts\build_mail_invoice_inventory_workspace.py
.\.venv\Scripts\python.exe scripts\review_mail_invoice_inventory_seed.py
.\.venv\Scripts\python.exe scripts\build_mail_invoice_io_bundle.py
```

既定では `fill_priority = P1` の行だけが bundle に入ります。個別指定したい場合は次です。

```powershell
.\.venv\Scripts\python.exe scripts\build_mail_invoice_io_bundle.py `
  --record-ref MAILBOX_PRIMARY `
  --record-ref SMTP_PRIMARY `
  --record-ref VISA_VPASS
```

## 5. 入力テスト

```powershell
.\secrets.ps1 ensure --spec .\docs\generated\mail_invoice_io.requirements.yaml --launch-form
```

表示された `http://127.0.0.1:...` を開き、不足している項目を入力します。

- 既に working CSV にある値はフォームへ初期値としては出さず、requirements の `record` 側に保持します
- requirements で不足と判定された項目だけが入力対象です
- 送信後は vault に保存され、フォームサーバーは停止します

## 6. 出力テスト

```powershell
.\secrets.ps1 render .\docs\generated\mail_invoice_io.template.yaml --stdout
```

ここで確認したいのは次です。

- `MAILBOX_PRIMARY` の `host` / `username` / `password` / `use_ssl`
- `SMTP_PRIMARY` の `host` / `from_address` / `password` / `starttls`
- `VISA_VPASS` の `login_url` / `username` / `password` / `auth_flow` / `otp_owner`

## 7. 現時点の挙動

- `build_mail_invoice_io_bundle.py` は `docs/overrides/*.csv` の `fill_priority` を見て対象を絞ります
- `candidate:*` は既定では含めません
- `mailbox_account` / `smtp_account` / `web_login` の入出力 round-trip は自動テスト済みです
- `VISA_VPASS` は `mfa_note` に `追加認証` があるため、bundle では `otp_owner` を入力対象に含めます

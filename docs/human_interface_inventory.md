# credential-vault 人間向けインターフェイスと認証台帳

この文書は、既存のスプレッドシート、Chatwork クローズドグループ、マイチャットに分散している情報を、
`credential-vault` へ段階移行する際の「人間が見る画面」と「非秘密メタデータ台帳」の整理です。

## 1. 方針

- 秘密値の正本候補は `credential-vault` に寄せる
- ただし移行中は、元の保存場所をすぐ消さず source locator として残す
- OTP の配送先、二重認証の通し方、ログイン確認結果は台帳化する
- TOTP seed、バックアップコード、実パスワード本文は台帳へ置かない

## 2. 人間向けインターフェイスの最小構成

ローカル Web UI を本命にしたとき、最低でも次の 4 画面が必要です。

### 2.1 棚卸し一覧

- `service_name`
- `entity_id`
- `account_label`
- `record_type`
- `migration_status`
- `vault_record_ref`
- `last_test_status`
- `last_tested_at`

### 2.2 資格情報詳細

- ログイン URL / host / port / username
- 会社コード / ユーザーコード
- `context_refs`
- 更新周期
- owner
- 説明

秘密値は既定で伏せ、明示操作でのみ表示します。

### 2.3 認証手順詳細

- `auth_flow`
- `otp_contact`
- `otp_owner`
- `recovery_url`
- `recovery_note`
- `mfa_note`
- `login_note`

ここは「どう突破するか」の approved path を残す場所です。
回避方法ではなく、正式な運用手順、必要デバイス、担当者、再発行窓口を記録します。

### 2.4 ログイン確認履歴

- `checked_at`
- `checked_by`
- `check_status`
- `check_method`
- `result_summary`
- `next_action`

`credential-vault` 本体には最新状態だけを持ち、履歴は非秘密の別台帳で持つ構成が扱いやすいです。

## 3. 推奨する台帳構成

移行中は、Google Sheets でもローカル CSV でもよいので、次の 3 シート構成を推奨します。

### 3.1 `資格情報台帳`

1 レコード 1 行で、秘密値以外の基礎情報を持ちます。

主な列:

- `migration_status`
- `source_type`
- `source_locator`
- `service_name`
- `record_type`
- `entity_id`
- `department_id`
- `account_label`
- `usage_purpose`
- `login_url`
- `tenant_code`
- `host`
- `port`
- `protocol`
- `username`
- `mailbox_name`
- `from_address`
- `use_ssl`
- `starttls`
- `company_code`
- `user_code`
- `classification`
- `rotation_days`
- `owner`
- `context_refs`
- `vault_record_ref`
- `notes`

### 3.2 `認証手順台帳`

MFA、OTP、復旧手順を `vault_record_ref` 単位で持ちます。

主な列:

- `vault_record_ref`
- `service_name`
- `account_label`
- `auth_flow`
- `otp_contact`
- `otp_owner`
- `required_device`
- `recovery_url`
- `recovery_note`
- `mfa_note`
- `login_note`

### 3.3 `ログイン確認履歴`

確認イベントを時系列で積みます。

主な列:

- `vault_record_ref`
- `checked_at`
- `checked_by`
- `target_kind`
- `check_status`
- `check_method`
- `result_summary`
- `next_action`

## 4. OTP / 二重認証の扱い

台帳化したいのは、次のような「正式な突破経路」です。

- OTP がどこに届くか
- 誰がそれを受け取れるか
- どの端末や認証アプリが必要か
- ログイン失敗時の連絡先
- 再発行や解除の URL
- 実施前に必要な社内確認

台帳に置かないもの:

- TOTP seed 本文
- バックアップコード本文
- SMS 認証コード本文
- 実パスワード本文

## 5. 移行フロー

1. 既存ソースを見て `資格情報台帳` に非秘密情報だけ書き出す
2. `service_name` / `entity_id` / `account_label` / `context_refs` を正規化する
3. `認証手順台帳` に MFA / OTP / recovery の手順を書く
4. 人間が `secrets add ...` または localhost 入力フォームで秘密値を vault へ登録する
5. `vault_record_ref` を台帳へ反映する
6. 実ログインや接続確認後、`secrets check ...` で最新状態を更新する
7. 履歴は `ログイン確認履歴` に追記する

`mail-invoice-processor` については、最初の叩き台として [mail_invoice_inventory_seed.md](/C:/Users/kouhe/credential-vault/docs/mail_invoice_inventory_seed.md) と `docs/seeds/*.csv` をそのまま使えます。
人間が実際に編集するのは `docs/overrides/*.csv`、review 対象は `docs/working/*.csv` にするのが安全です。
`overrides` の `fill_priority` は着手順、`fill_hint` は最初に確認したい元ソースや入力観点のメモです。
実際の localhost 入力と render 確認は [inventory_io_test.md](/C:/Users/kouhe/credential-vault/docs/inventory_io_test.md) に沿って進めます。

## 6. すぐ使うコマンド

```powershell
.\secrets.ps1 add login freee-admin `
  --entity-id C02 `
  --account-label "経理管理者" `
  --login-url "https://accounts.secure.freee.co.jp/" `
  --username "admin@example.com" `
  --auth-flow "password_plus_totp" `
  --otp-owner "経理責任者" `
  --recovery-url "https://accounts.secure.freee.co.jp/password_resets/new" `
  --stdin

.\secrets.ps1 check rec_web_001 `
  --status ok `
  --by "kouhe" `
  --note "TOTP と会社コードでログイン成功"
```

# mail-invoice-processor 移行 seed

この文書は、`mail-invoice-processor` から現在把握できる credential 候補を、
非秘密ソースだけで seed 台帳へ起こすためのメモです。

## 1. 使っているソース

- `../mail-invoice-processor/config/local.runtime.requirements.yaml`
- `../mail-invoice-processor/docs/service-automation-inventory.csv`
- `../mail-invoice-processor/README.md`
- `../mail-invoice-processor/tests/*.py` にある公開ログイン URL や vendor rule 例

実値が入る可能性のある `config/local.runtime.yaml` は参照しません。

## 2. 生成される seed と作業ファイル

- [mail_invoice_credential_inventory_seed.csv](/C:/Users/kouhe/credential-vault/docs/seeds/mail_invoice_credential_inventory_seed.csv)
- [mail_invoice_auth_step_inventory_seed.csv](/C:/Users/kouhe/credential-vault/docs/seeds/mail_invoice_auth_step_inventory_seed.csv)
- [mail_invoice_login_check_inventory_seed.csv](/C:/Users/kouhe/credential-vault/docs/seeds/mail_invoice_login_check_inventory_seed.csv)
- [mail_invoice_credential_inventory_override.csv](/C:/Users/kouhe/credential-vault/docs/overrides/mail_invoice_credential_inventory_override.csv)
- [mail_invoice_auth_step_inventory_override.csv](/C:/Users/kouhe/credential-vault/docs/overrides/mail_invoice_auth_step_inventory_override.csv)
- [mail_invoice_login_check_inventory_override.csv](/C:/Users/kouhe/credential-vault/docs/overrides/mail_invoice_login_check_inventory_override.csv)
- [mail_invoice_credential_inventory_working.csv](/C:/Users/kouhe/credential-vault/docs/working/mail_invoice_credential_inventory_working.csv)
- [mail_invoice_auth_step_inventory_working.csv](/C:/Users/kouhe/credential-vault/docs/working/mail_invoice_auth_step_inventory_working.csv)
- [mail_invoice_login_check_inventory_working.csv](/C:/Users/kouhe/credential-vault/docs/working/mail_invoice_login_check_inventory_working.csv)
- [mail_invoice_io.requirements.yaml](/C:/Users/kouhe/credential-vault/docs/generated/mail_invoice_io.requirements.yaml)
- [mail_invoice_io.template.yaml](/C:/Users/kouhe/credential-vault/docs/generated/mail_invoice_io.template.yaml)
- [mail_invoice_io.summary.yaml](/C:/Users/kouhe/credential-vault/docs/generated/mail_invoice_io.summary.yaml)

## 3. 推奨コマンド

```powershell
.\.venv\Scripts\python.exe scripts\build_mail_invoice_inventory_workspace.py
```

review は次です。

```powershell
.\.venv\Scripts\python.exe scripts\review_mail_invoice_inventory_seed.py
```

入出力テスト bundle は次です。

```powershell
.\.venv\Scripts\python.exe scripts\build_mail_invoice_io_bundle.py
```

## 4. 現時点の見方

- `seed_from_requirement`
  `mail-invoice-processor` が実行時に必須としている credential
- `candidate_from_service_inventory`
  実装計画や service inventory に出ているが、まだ requirements には入っていない候補
- `candidate:*`
  まだ vault の real `record_id` がない候補識別子
- `override`
  人間が埋める差分。blank は seed 維持、`__CLEAR__` は意図的に空へ戻す
  `fill_priority` は着手順、`fill_hint` は最初に確認したい入力メモ
- `working`
  seed と override を重ねた、実際に review する作業用ファイル
- `generated`
  working から作る入出力テスト用 bundle。`ensure` と `render` をすぐ試せる

## 5. 人間が次に埋める項目

- まず `docs/overrides/*.csv` の `fill_priority = P1` を上から埋める
- `fill_hint` を見て、source locator や auth_flow の確認先を決める
- `source_type` と `source_locator` を実際のスプシ / Chatwork / マイチャットへ寄せる
- `entity_id` と `owner` を実運用に合わせて入れる
- `host` / `port` / `protocol` / `use_ssl` / `from_address` / `starttls` のような非秘密設定も working に寄せる
- `auth_flow` / `otp_contact` / `otp_owner` / `recovery_note` を認証手順台帳に入れる
- ログイン確認後に `secrets check` と確認履歴台帳を更新する

2026-04-03 時点の review では、主に次が TODO です。

- `MAILBOX_PRIMARY` / `SMTP_PRIMARY` / `VISA_VPASS` の `owner` と `entity_id`
- `FUJIFILM_BI_DIRECT` / `SAGAWA_SMART_CLUB` / `SANICLEAN` / `GMO` / `JCB` の candidate 解消
- 各 `web_login` の `auth_flow`
- `GMO` / `JCB` の OTP / MFA 担当情報

## 6. 注意

- seed の `vault_record_ref` は、未移行候補では `candidate:*` を使っています
- これは本番の `record_id` ではありません
- 実際に vault 登録したら、`candidate:*` を `rec_*` または alias へ置き換えます
- 基本は `docs/overrides/*.csv` を編集し、`docs/working/*.csv` は再生成物として扱います
- 入出力テストは [inventory_io_test.md](/C:/Users/kouhe/credential-vault/docs/inventory_io_test.md) の手順で進めます

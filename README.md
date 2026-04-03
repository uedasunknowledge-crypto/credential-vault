# credential-vault

NH1 上で認証情報を安全に一元管理するためのローカル vault 基盤です。
各プロジェクトは `secrets` CLI を通じて必要な値を取得し、人間は同じ CLI で追加・更新・参照を行います。

## 現在の状態

- 2026-04-02 時点で設計と Python CLI 骨格、暗号化保存の初期実装まで追加済み
- 依存前提の P10 `nh1-infra` は `../no-tion-plan/TASKS.md` 上で 2026-03-27 に完了
- 実データやマスターパスワードはこのリポジトリに含めない

## 目標

- `vault.enc` を Git 管理外で保持し、NH1 ローカルのみで運用する
- `secrets get/set/list/view` を中心に 1Password CLI に近い操作感を提供する
- P1a-P2b の情報を対象にし、P3 は原則として対象外にする
- 自動処理でも使えるようにしつつ、平文の長期保存は避ける

## ドキュメント

- [初期設計](/C:/Users/kouhe/credential-vault/docs/architecture.md)
- [拡張要件と管理モデル](/C:/Users/kouhe/credential-vault/docs/expanded_requirements.md)
- [人間向けインターフェイスと認証台帳](/C:/Users/kouhe/credential-vault/docs/human_interface_inventory.md)
- [inventory 入出力テスト](/C:/Users/kouhe/credential-vault/docs/inventory_io_test.md)
- [段階移行とバックアップ方針](/C:/Users/kouhe/credential-vault/docs/migration_strategy.md)
- [business-master-sync 連携案](/C:/Users/kouhe/credential-vault/docs/business_master_sync_contract.md)
- [mail-invoice-processor 連携ガイド](/C:/Users/kouhe/credential-vault/docs/mail_invoice_processor_integration.md)
- [mail-invoice 移行 seed](/C:/Users/kouhe/credential-vault/docs/mail_invoice_inventory_seed.md)
- [CLI利用イメージ](/C:/Users/kouhe/credential-vault/docs/usage_examples.md)

## 想定配置

```text
/home/horizontalhold/auto_project/credential-vault/
├── vault.enc
└── secrets
```

このリポジトリには主に CLI 実装と設計資料を置きます。`vault.enc` 本体は GitHub にコミットしません。

## ローカル開発

Windows 側ではリポジトリ直下の `.venv` を使って開発できます。

```powershell
.\.venv\Scripts\python.exe -m pytest
.\secrets.ps1 status
.\secrets.ps1 init
.\secrets.ps1 check MAILBOX_PRIMARY --status ok --by kouhe --note "接続確認済み"
.\.venv\Scripts\python.exe scripts\build_mail_invoice_inventory_workspace.py
.\.venv\Scripts\python.exe scripts\review_mail_invoice_inventory_seed.py
.\.venv\Scripts\python.exe scripts\build_mail_invoice_io_bundle.py
```

`secrets.ps1` と `secrets.cmd` は、`.venv` の Python から `credential_vault.cli` を直接起動する開発用ラッパーです。

`docs/overrides/*.csv` には `fill_priority` と `fill_hint` が入り、移行時にどの行から埋めるべきかを先に見られます。実際の review は `docs/working/*.csv` を見ます。
`docs/generated/mail_invoice_io.requirements.yaml` と `docs/generated/mail_invoice_io.template.yaml` を作ると、localhost フォーム入力と render 出力をまとめて試せます。

## mail-invoice-processor 連携

`mail-invoice-processor` を sibling repo として置いている場合は、vault 経由の実行ラッパーを使えます。

```powershell
.\scripts\run_mail_invoice_processor_with_vault.ps1 -Module url_downloader --max-items 10
.\scripts\run_mail_invoice_processor_with_vault.ps1 -Module main --max-messages 10 --date 2026-03-31
```

runtime YAML だけを生成して確認したい場合は次を使います。

```powershell
.\scripts\render_mail_invoice_processor_runtime.ps1
```

`mail-invoice-processor\config\local.runtime.requirements.yaml` が存在する場合は、wrapper が実行前に `secrets ensure` を呼びます。不足 credential があると localhost の入力フォーム URL を出して、そのまま vault へ保存できます。既存 record に `MAILBOX_PRIMARY` のような alias がまだ無くても、`service_name` `entity_id` `account_label` `context_refs` などの metadata が一意に合えば自動で既存 record を拾って alias を同期します。

`web_login` では `auth_flow` `otp_contact` `otp_owner` `recovery_url` `recovery_note` を持てるので、OTP や二重認証の正式な運用手順も秘密値と紐づけて管理できます。`secrets check` でログインや接続確認の最新結果を記録し、履歴そのものは `docs/examples/login_check_inventory_template.csv` のような非秘密台帳へ残す運用が安全です。

詳細は [mail_invoice_processor_integration.md](/C:/Users/kouhe/credential-vault/docs/mail_invoice_processor_integration.md) を参照してください。

## 現在のローカル状態

- 2026-04-02 時点で Windows 開発環境の `.venv` を整備済み
- `.\.venv\Scripts\python.exe -m pytest` で 35 件のテストが通過
- `scrypt` は Windows/OpenSSL の既定メモリ制限を超えないよう補正済み

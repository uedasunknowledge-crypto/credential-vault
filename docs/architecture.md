# credential-vault 初期設計

## 1. 背景

`credential-vault` は、NH1 上に散在している API キーやログイン情報を 1 か所に集約し、各プロジェクトが共通 CLI から安全に取得できるようにするための基盤です。

2026-03-26 の引継ぎでは P10 `nh1-infra` 未整備がブロッカーでしたが、`../no-tion-plan/TASKS.md` では 2026-03-27 に完了へ更新されています。本設計は、その前提が満たされた状態で着手するものとします。

なお、2026-04-02 時点で要件は「API キー保管」に加えて、「Web サイトの ID/パスワード管理」「更新・失効・重複管理」「通知と半自動運用」まで拡張されています。詳細は [拡張要件と管理モデル](/C:/Users/kouhe/credential-vault/docs/expanded_requirements.md) を参照します。

## 2. 設計方針

### 2.1 守るもの

- `vault.enc` が誤って GitHub に載らないこと
- NH1 上のディスクに保存された認証情報が平文で残らないこと
- 日常運用で `secrets` CLI だけを覚えれば使えること
- 人間向けの更新作業と、プロジェクトからの参照を同じデータモデルで扱えること

### 2.2 今回あえて守らないもの

- P3 相当の極めて機微な情報の長期保管
- 複数人同時編集
- クラウド同期
- root 権限奪取済みホストからの防御
- GUI アプリ

### 2.3 運用前提

- vault 本体は NH1 ローカルにのみ配置する
- 実際の秘密情報の登録は人間が行う
- AI は設計と実装のみ担当し、秘密値そのものには触れない
- 主な利用者は単一運用者で、各プロジェクトは NH1 上で動く

## 3. ユースケース

### 3.1 人間の操作

1. `secrets set NOTION_TOKEN` で値を登録する
2. `secrets list` で登録状況を確認する
3. `secrets view NOTION_TOKEN` で内容を確認する
4. `secrets set NOTION_TOKEN` を再実行して値を更新する

### 3.2 自動処理の操作

1. プロジェクトが `secrets get NOTION_TOKEN` を呼ぶ
2. CLI が vault を参照して値を標準出力へ返す
3. 失敗時は終了コードで原因を判別できる

### 3.3 人間のパスワード管理

1. 運用者がログイン URL、会社コード、ユーザーコード、パスワードを登録する
2. 更新期限が近いレコードを一覧で確認する
3. 更新後に新しい値へ差し替え、旧値を失効または廃止扱いにする

### 3.4 半自動運用

1. NH1 が期限到来や重複候補を検知する
2. 人間へ通知する
3. 人間が確認後に更新または失効を反映する

## 4. 機能要件

### 4.1 Phase 1 の必須機能

- `get`: 指定キーの値だけを返す
- `set`: キーを新規登録または更新する
- `list`: キー名とメタデータだけを表示する
- `view`: 値とメタデータを表示する
- vault 初期化
- vault 整合性チェック

### 4.2 Phase 2 で追加する機能

- `lock` / `unlock`: セッションを明示的に制御する
- `status`: セッション状態を表示する
- `doctor`: 実行環境の健全性確認を行う

### 4.3 メタデータ

各エントリは最低限次の情報を持ちます。

- `value`
- `service_name`
- `entity_id`
- `account_label`
- `classification` (`P1a`, `P1b`, `P2a`, `P2b`, `P3`)
- `description`
- `tags`
- `created_at`
- `updated_at`

将来的には以下も持ちます。

- `record_type`
- `department_id`
- `usage_purpose`
- `status`
- `rotation_policy`
- `expires_at`
- `last_verified_at`
- `fingerprint`

同じサービスに複数アカウントがある前提なので、`service_name` だけで一意とみなさず、`entity_id` と `account_label` を識別子として使います。

### 4.4 非機能要件

- NH1 の 2GB RAM 環境で動作する
- vault が壊れたときに破損を検知できる
- シェル履歴に値を残しにくい操作を用意する
- Linux 上のファイル権限で保護できる
- Python ベースで保守しやすい

## 5. セキュリティ方針

### 5.1 データ区分

- `P1a`: システム設定値
- `P1b`: プロジェクト用トークン
- `P2a`: 個人アカウント情報
- `P2b`: 財務系の認証情報
- `P3`: 原則として vault 対象外

### 5.2 脅威モデル

想定する脅威:

- `vault.enc` の流出
- 誤コミット
- 端末上の平文ファイル取り残し
- シェル履歴経由の漏えい

想定外または限定的にしか防げない脅威:

- root 権限を持つ攻撃者
- キーロガー
- すでに侵害された稼働中ホスト
- 物理アクセス済みかつ運用者ログイン中の端末

### 5.3 取り扱いルール

- `vault.enc` は Git 管理外
- `.env` や一時ファイルに秘密値を書き出さない
- `set` は引数直書きより `--stdin` または対話入力を推奨する
- `list` は値を表示しない
- `view` は対話利用を前提とし、非対話では明示フラグを要求する

## 6. アーキテクチャ案

### 6.1 採用案

初期版では Python 3.10+ で CLI を実装し、vault は 1 ファイルの暗号化コンテナとして扱います。

- 言語: Python
- 暗号化: `cryptography` ライブラリの `AES-256-GCM`
- 鍵導出: `scrypt`
- データ形式: 暗号化前は JSON、保存時は暗号化エンベロープ JSON

この構成を選ぶ理由:

- NH1 上で追加の常駐サービスや GPG/age 前提を持ち込まなくてよい
- 復号後データの構造をシンプルに保てる
- AES-GCM で機密性と完全性を同時に確保できる
- `scrypt` で総当たり耐性を持たせやすい

### 6.2 見送る案

- GPG ベース: 利用者体験が重く、鍵管理が分散しやすい
- age ベース: 鍵ファイル運用は魅力があるが、人間向けマスターパスワード中心の要件とややずれる
- SQLite 暗号化: データモデルとしては便利だが初期版には過剰

## 7. Vault ファイル形式

### 7.1 保存形式

`vault.enc` はメタデータ付きの JSON エンベロープとします。

```json
{
  "version": 1,
  "cipher": "AES-256-GCM",
  "kdf": {
    "name": "scrypt",
    "n": 32768,
    "r": 8,
    "p": 1,
    "salt_b64": "..."
  },
  "nonce_b64": "...",
  "ciphertext_b64": "...",
  "created_at": "2026-04-02T00:00:00Z",
  "updated_at": "2026-04-02T00:00:00Z"
}
```

### 7.2 復号後データ

```json
{
  "vault_version": 1,
  "entries": {
    "NOTION_TOKEN": {
      "value": "secret-value",
      "classification": "P1b",
      "description": "Notion integration token",
      "tags": ["notion", "infra"],
      "created_at": "2026-04-02T00:00:00Z",
      "updated_at": "2026-04-02T00:00:00Z"
    }
  }
}
```

### 7.3 設計上の注意

- キー名は大文字スネークケースを基本にする
- 機密値以外のメタデータも同じコンテナ内で暗号化する
- 将来の移行に備えて `version` を先頭に持つ
- 更新時はテンポラリファイルへ書き出してから atomic rename する

## 8. アンロック方式

### 8.1 目標形

運用が安定した後の目標形は「手動アンロック済みセッション」を前提にします。

- `secrets unlock --ttl 8h`
- メモリ上に復号鍵を保持する軽量エージェントを起動
- `secrets get/set/list/view` はローカルソケット経由でエージェントに問い合わせる
- TTL 経過または `secrets lock` で破棄する

この方式の意図:

- マスターパスワードを `.env` や systemd ユニットへ置かずに済む
- 日中の運用では毎回パスワードを打たなくてよい
- 平文鍵をディスクにキャッシュしない

### 8.2 Phase 1 の暫定運用

Phase 1 ではエージェントをまだ持たず、各コマンド実行時にマスターパスワード入力を求める暫定運用でも開始できます。

- `get` は非対話利用を優先し、ロック状態なら即失敗させる
- `set/list/view` は対話端末でのみパスワード入力を受け付ける
- この運用で支障が大きければ Phase 2 の優先度を上げる

### 8.3 ロック時の挙動

- 対話端末で `get` / `view` を実行した場合はアンロックを促す
- 非対話実行でアンロックされていない場合は終了コード `20` で失敗する
- systemd や cron から使うジョブは、事前にアンロック済みであることを前提にする

### 8.4 将来拡張

NH1 の無人再起動後も自動復旧したい場合は、後続フェーズで machine-bound unlock を追加します。

候補:

- NH1 ローカル限定の鍵ファイル
- TPM や FIDO2 等のハードウェア支援
- 複数ラップ鍵方式

この機能は初期版では見送り、まずは運用を単純化します。

## 9. CLI 仕様

### 9.1 コマンド一覧

```text
secrets init
secrets unlock [--ttl 8h]
secrets lock
secrets status
secrets get KEY
secrets set KEY [VALUE] [--stdin] [--classification P1b] [--description "..."] [--tag x]
secrets list [--classification P1b] [--tag notion]
secrets view KEY
secrets delete KEY
secrets doctor
```

### 9.2 コマンドの責務

- `init`: 空の vault を作成する
- `unlock`: マスターパスワードでセッションを開く
- `lock`: セッションを破棄する
- `status`: セッション状態と vault パスを表示する
- `get`: 値だけを標準出力へ返す
- `set`: 値とメタデータを登録または更新する
- `list`: 値を除く一覧を表示する
- `view`: 値を含む詳細を表示する
- `delete`: 不要なキーを削除する
- `doctor`: ファイル権限、vault 破損、依存不足を確認する

拡張フェーズでは、`revoke`、`due list`、`rotate begin`、`rotate confirm` のようなライフサイクル管理コマンドを追加します。

### 9.3 入出力ポリシー

- `get` は標準出力に値のみを返す
- `list` は表形式または `--json` を返す
- エラーは標準エラー出力に書く
- 値を含む詳細表示は `view` に寄せ、`get` はスクリプト向けに固定する

### 9.4 推奨終了コード

- `0`: 成功
- `2`: 引数エラー
- `20`: vault がロック中
- `21`: キー未登録
- `30`: vault 破損
- `40`: 権限エラー
- `50`: 内部エラー

## 10. 実装構成案

```text
src/credential_vault/
├── __init__.py
├── cli.py
├── config.py
├── models.py
├── crypto.py
├── vault_store.py
├── session_agent.py
├── commands/
│   ├── init_cmd.py
│   ├── unlock_cmd.py
│   ├── get_cmd.py
│   ├── set_cmd.py
│   ├── list_cmd.py
│   └── view_cmd.py
└── utils/
    ├── io.py
    └── time.py
```

補助ディレクトリ:

```text
tests/
├── test_crypto.py
├── test_vault_store.py
├── test_cli_get.py
└── test_cli_set.py
```

## 11. 運用方針

### 11.1 配置

- リポジトリ: 実装コードと設計のみ
- NH1 実体: `/home/horizontalhold/auto_project/credential-vault/`
- vault: `/home/horizontalhold/auto_project/credential-vault/vault.enc`
- セッションソケット: `/run/user/<uid>/credential-vault/agent.sock`

### 11.2 バックアップ

- `vault.enc` のバックアップは暗号化済みのまま取得する
- 復号後 JSON をバックアップ対象にしない
- リストア手順は P10 の復旧ドキュメントに寄せて別途整備する

### 11.3 監査と更新

- 少なくとも `updated_at` は全件保持する
- 将来フェーズで `updated_by` と操作ログを追加できる余地を残す
- 初期版では詳細監査ログよりも安全な保存と取得を優先する

### 11.4 UI 方針

- 機械利用の主経路は CLI
- 人間向け UI の本命は NH1 ローカルの Web アプリ
- Chatwork は秘密値を表示しない通知チャネルとしてのみ使う
- `business-master-sync` とは非秘密メタデータだけを連携し、秘密値は vault 側に残す

## 12. リスク

- NH1 再起動後は人手で `unlock` が必要
- 単一ファイル更新なので、同時編集はロック制御が必要
- マスターパスワード紛失時の復旧手順を別途決める必要がある
- 長すぎる TTL は利便性と引き換えにリスクを増やす

## 13. 実装フェーズ案

### Phase 1

- vault フォーマット
- `init/get/set/list/view`
- atomic write
- 基本テスト

### Phase 2

- `unlock/lock/status`
- 軽量セッションエージェント
- 非対話向け終了コード整理

### Phase 3

- `delete/doctor`
- バックアップ補助
- 監査メタデータ強化

## 14. 未決定事項

- `unlock` を最初から実装するか、Phase 1 の時点では対話プロンプトのみで始めるか
- `view` に非対話出力を許す条件をどうするか
- `updated_by` を最初から持つか
- バックアップ配置先をどこにするか
- machine-bound unlock を将来どの方式で足すか

## 15. 次の一手

1. `src/credential_vault` の最小骨格を作る
2. `vault_store.py` と `crypto.py` を先に実装する
3. `get/set/list/view` の CLI テストを先に書く
4. `unlock` の実装タイミングは Phase 1 完了時点で再判断する

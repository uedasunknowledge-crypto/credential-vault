# credential-vault 段階移行とバックアップ方針

この文書は、現時点での正本がスプレッドシート、Chatwork のクローズドグループ、マイチャットに分散している前提で、
`credential-vault` へ無理なく移行するための運用方針を整理したものです。

## 1. 現時点の前提

- 既存の正本はスプレッドシートや Chatwork に残っている
- NH1 は低スペックで、障害リスクを前提にすべき
- そのため、すぐに旧保管先を破棄する運用は取らない

## 2. 段階移行の方針

### Phase 0: 既存正本を維持したまま vault を併設する

- まずは `credential-vault` へ登録を始める
- 既存のスプシや Chatwork はまだ正本扱いのまま残す
- 実行時だけ `credential-vault` を参照する経路を増やす
- requirement 側の `record_ref` alias が未整備でも、metadata が一意に合う既存 record は `ensure` が拾って alias を同期する

この段階のゴール:

- YAML や `.env` に平文を新規追加しない
- `mail-invoice-processor` などから `credential-vault` を参照できる

### Phase 1: 実行正本を vault に寄せる

- 実運用の取得や自動処理は `credential-vault` を優先して使う
- 旧保管先は参照専用の退避場所として残す
- 更新が入った値はまず vault へ反映する

この段階のゴール:

- 新しい認証情報は vault が最初の保存先になる
- 既存のスプシや Chatwork は fallback 参照に限定する

### Phase 2: バックアップ確立後に旧正本を破棄する

- 安全なバックアップ経路を整備する
- 復旧手順を確認する
- その後にだけ旧保管先を順次削除する

この段階のゴール:

- vault が唯一の正本になる
- 旧平文保管先を段階的に閉じる

## 3. まず置き換えるべきもの

優先順位は次が現実的です。

1. `config/local.runtime.yaml` の password 類
2. `.env` の API キーや SMTP/POP パスワード
3. 自動処理で定期的に使う portal ログイン
4. 人間がコピペで頻繁に使う共有アカウント

## 4. レコード単位の考え方

人間の入出力では、次のように「1セットの資格情報」として扱います。

- `mailbox_account`
  - `host`
  - `port`
  - `protocol`
  - `username`
  - `password`
  - `use_ssl`
- `smtp_account`
  - `host`
  - `port`
  - `username`
  - `password`
  - `from_address`
  - `use_ssl`
  - `starttls`
- `web_login`
  - `login_url`
  - `username`
  - `password`
  - `company_code`
  - `user_code`

内部でフィールド分離されていても、人間に見せる単位は 1 レコードを基本にします。

## 5. 複数候補をどう特定するか

同じメールアドレスや API キー系でも、法人、事業、プロジェクト、用途で複数存在します。

そのため、`credential-vault` では少なくとも次で特定します。

- `service_name`
- `entity_id`
- `department_id`
- `account_label`
- `usage_purpose`
- `context_refs`

`context_refs` には `business-*` 系の共通語や参照キーを入れます。

例:

- `biz:C02`
- `project:mail-invoice`
- `tool:billone`
- `service_scope:invoice-fetch`

移行台帳は、少なくとも次の 3 つに分けると安全です。

- `資格情報台帳`: source locator と credential metadata
- `認証手順台帳`: OTP / MFA / recovery の正式手順
- `ログイン確認履歴`: 接続確認や実ログイン確認の時系列履歴

## 6. バックアップ方針

現時点では、バックアップ未整備のまま「唯一の正本」へ一気に寄せるのは避けます。

やる順番は次です。

1. vault 本体を安定運用する
2. 復旧に必要な最低手順を文章化する
3. 安全な保管先へ暗号化バックアップを複製する
4. 復元テストを行う
5. 旧正本を削除する

## 7. 現時点のおすすめ運用

- 新規の平文 credential は `.env` や YAML へ増やさない
- `mail-invoice-processor` など実行系から先に vault 参照へ移す
- 人間用の参照は当面 CLI 中心でよい
- 旧正本はまだ残すが、更新の第一反映先は徐々に vault に寄せる

## 8. 次にやること

- 実 credential を使わない形で localhost 入力フォームの手動確認手順を固める
- 既存のスプシや Chatwork から移す候補を棚卸しし、`service_name` / `entity_id` / `account_label` / `context_refs` を先に整える
- 安全なバックアップ先が用意できるまで、どの credential を旧正本にも残すかを運用ルール化する

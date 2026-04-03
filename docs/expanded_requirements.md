# credential-vault 拡張要件と管理モデル

この文書は、2026-04-02 に追加された2つの目標を、実装可能な設計要件へ落とし込むための整理です。

## 1. 今回の目標の再定義

### 1.1 目標1

NH1 が各種サイトや API を扱うときに、認証情報の登録、取得、更新、重複排除、失効管理までを安全に扱えること。

加えて、以下を満たす必要があります。

- 自動または半自動で運用できる
- 更新や失効の前後で確認フローを持てる
- AI 間や NH1 内の受け渡しは暗号化または秘密値を直接渡さない方式にする

### 1.2 目標2

人間も安全にログイン情報を管理できること。

管理対象:

- ログイン URL
- 会社コード
- ユーザーコード
- パスワード
- 更新周期
- 最新版かどうか

想定インターフェイス候補:

- ローカル Web アプリ
- Chatwork 応答

## 2. 結論から見た設計方針

この要件だと、単なる「暗号化メモ帳」では足りません。
必要なのは、秘密値そのものに加えて、状態、更新期限、通知先、承認要否まで持つ「秘密情報台帳」です。

そのため、`credential-vault` は次の 3 層で設計します。

1. vault 本体
2. 秘密情報のライフサイクル管理層
3. 人間・自動処理向けインターフェイス層

## 3. 管理対象のデータモデル

### 3.1 レコード種別

最低でも次の 3 種類を持てるようにします。

- `api_secret`: API キー、アクセストークン、リフレッシュトークン
- `web_login`: Web サービスのログイン情報
- `machine_secret`: NH1 内部やサービス間連携で使う共有秘密

ただし、人間が「1つの資格情報セット」として扱いたいメール系は別レコードとして持てる方が運用しやすいため、次も追加候補ではなく実装対象に寄せます。

- `mailbox_account`: POP3 / IMAP の server, account, password をまとめた受信資格情報
- `smtp_account`: SMTP の server, account, password, from_address をまとめた送信資格情報

### 3.2 共通項目

すべてのレコードに共通で持たせる項目:

- `record_id`
- `record_type`
- `service_name`
- `entity_id`
- `department_id`
- `account_label`
- `usage_purpose`
- `context_refs`
- `classification`
- `status`
- `description`
- `tags`
- `owner`
- `created_at`
- `updated_at`
- `last_verified_at`
- `last_tested_at`
- `last_tested_by`
- `last_test_status`
- `last_test_note`
- `rotation_policy`
- `expires_at`
- `revoked_at`
- `fingerprint`

この 4 項目を持たせる理由は、同じサービスでも複数の ID/パスワードを持つ前提があるためです。

`context_refs` は `business-*` 系の共通語や、事業・プロジェクト・業務文脈の参照キーを持つための項目です。

例:

- `biz:C02`
- `project:mail-invoice`
- `tool:billone`
- `service_scope:invoice-fetch`

例:

- 同じ `freee` でも法人ごとにアカウントが違う
- 同じ `Google` でも管理者用、閲覧用、運用用がある
- 同じサービスでも本番用とテスト用で別アカウントを使う

### 3.3 `api_secret` の項目

- `secret_key_name`
- `secret_value`
- `scope`
- `issuer`
- `environment`

### 3.4 `web_login` の項目

- `login_url`
- `tenant_code`
- `company_code`
- `user_code`
- `username`
- `password`
- `auth_flow`
- `otp_contact`
- `otp_owner`
- `recovery_url`
- `recovery_note`
- `mfa_note`
- `login_note`

この形にしておくと、「会社コードがあるサービス」と「メールアドレスだけで入るサービス」を同じ vault に載せられます。
加えて、同一サービスに複数アカウントがあっても、`entity_id`、`account_label`、`usage_purpose` で区別できます。
さらに、OTP や二重認証の「正式な通し方」を構造化して残せるため、担当者が変わっても確認経路を引き継ぎやすくなります。

### 3.5 `machine_secret` の項目

- `consumer`
- `provider`
- `secret_value`
- `transport_mode`

### 3.6 `mailbox_account` の項目

- `host`
- `port`
- `protocol`
- `username`
- `password`
- `use_ssl`
- `mailbox_name`

### 3.7 `smtp_account` の項目

- `host`
- `port`
- `username`
- `password`
- `from_address`
- `use_ssl`
- `starttls`

## 4. 状態管理

### 4.1 状態

各レコードは少なくとも次の状態を持ちます。

- `draft`: 作成中
- `active`: 利用中
- `rotation_due`: 更新期限が近い
- `rotating`: 更新作業中
- `revoked`: 失効済み
- `retired`: 利用終了

### 4.2 状態遷移

基本の流れ:

`draft -> active -> rotation_due -> rotating -> active`

失効や廃止:

`active -> revoked`

`revoked -> retired`

### 4.3 ここで得られる運用上の利点

- 「今使っていい値か」が分かる
- 失効済みの値を誤用しにくい
- 更新作業中の値を明示できる
- 人間向けのパスワードリマインダーにもそのまま使える

## 5. 重複管理

### 5.1 何を重複とみなすか

重複判定キーは種別ごとに分けます。

- `api_secret`: `service_name + environment + secret_key_name`
- `web_login`: `service_name + entity_id + department_id + account_label + login_url + tenant_code/company_code + user_code/username`
- `machine_secret`: `provider + consumer + transport_mode`

### 5.2 重複検知の方法

- 平文そのものではなく正規化済みメタデータで重複候補を検出する
- 秘密値についてはハッシュ化した `fingerprint` で変更有無だけを追う
- 完全自動でマージせず、候補を提示して人間確認にする

### 5.3 変更検知

値が更新されたら:

- `updated_at` を更新
- `last_verified_at` を更新
- 旧値は即削除ではなく、短期の履歴保管または一時退避を選べるようにする

ただし、履歴保管は秘密値の複製を増やすので、初期版では「旧値を残さない」を既定にする方が安全です。

## 6. 更新・失効のマネージメント

### 6.1 運用モード

各レコードまたはサービスごとに運用モードを持たせます。

- `manual`: 人間が手で更新する
- `assisted`: AI/NH1 が更新手順を案内し、最後は確認して反映する
- `automatic`: API で自動更新できる

### 6.2 半自動フロー

半自動では次の流れを想定します。

1. 更新期限または失効予定を検知する
2. 通知を出す
3. 人間が確認する
4. 新しい値を入力または取り込みする
5. 既存レコードを更新し、必要なら旧値を失効扱いにする

### 6.3 自動フロー

自動更新できるのは API ベースの一部に限定します。

例:

- リフレッシュトークンからアクセストークンを再取得する
- サービス API 経由で短命トークンを払い出す

この場合でも以下は必須です。

- 成功/失敗の監査記録
- 更新前後の状態遷移
- 失敗時の通知

### 6.4 失効

失効は `delete` ではなく `revoke` を基本にします。

理由:

- 誤って使い続ける事故を減らせる
- 「今は無効」を状態として残せる
- 外部サービス側の無効化と内部台帳の同期を取りやすい

## 7. AI 間・NH1 間の受け渡し方針

### 7.1 原則

最も大事な原則は、「AI に秘密値を渡さない」です。

AI 間や別プロセスへの連携は、まず次の順で考えます。

1. 秘密値ではなく `record_id` や参照名だけを渡す
2. 実際の取得は NH1 内の broker が行う
3. どうしても外に出す必要があるときだけ暗号化ペイロードを使う

### 7.2 NH1 内の推奨方式

NH1 内はネットワーク転送よりも、ローカル IPC を優先します。

- Unix Domain Socket
- OS のファイル権限
- 起動ユーザー制限

これなら「平文を別ファイルへ書き出して渡す」必要が減ります。

### 7.3 AI 間・ホスト間でどうしても渡す場合

どうしても引き渡しが必要な場合だけ、短命な暗号化バンドルを使います。

候補:

- `age` による受信者公開鍵暗号化
- `cryptography` による一時鍵ベースの envelope encryption

バンドルに含めるべきなのは最低限です。

- `record_id`
- `operation`
- `expires_at`
- 暗号化済み payload

避けるべきこと:

- AI の会話ログに秘密値を貼る
- Git 管理下のファイルに一時出力する
- Chatwork や Notion に秘密値をそのまま送る

### 7.4 実用上の推奨

初期版では「AI 間共有」は参照名だけに留めるのが安全です。
秘密値の実取得は常に NH1 上の CLI または broker だけが担当する設計がよいです。

## 8. 人間向けインターフェイス方針

### 8.1 結論

本命はローカル Web アプリです。
Chatwork は通知専用の補助チャネルに留めるのが安全です。

### 8.2 Web アプリを本命にする理由

- URL、会社コード、ユーザーコード、パスワード、期限などを一覧しやすい
- 同一サービス配下の複数アカウントをグループ表示しやすい
- マスク表示、再表示、コピー、更新確認が作りやすい
- 更新期限や状態の絞り込みがしやすい
- 将来、承認ダイアログや監査ログを載せやすい

### 8.3 Chatwork を主画面にしない理由

- チャットは秘密値の保管場所に向かない
- 誤送信や転送のリスクが高い
- 一覧性や状態管理に弱い
- 自動削除があっても配信面のリスクは残る

### 8.4 Chatwork の安全な使い方

Chatwork で送るのは通知だけにします。

送ってよい例:

- 「freee 管理者アカウントのパスワード更新期限が 7 日後」
- 「NOTION_TOKEN の更新処理が失敗」
- 「承認待ちの更新が 1 件ある」

送らないもの:

- パスワード本文
- API キー全文
- ユーザーコード全文
- ログイン URL に埋め込まれた機微パラメータ

## 9. 推奨 UI 構成

### 9.1 Phase 1

- CLI のみ
- 人間向けパスワード管理も CLI で登録・確認
- 期限到来は一覧や `doctor` 系コマンドで確認
- `service_name` 単位ではなく `service_name + account_label` 単位で扱う

### 9.2 Phase 2

- NH1 ローカル限定の Web アプリ
- ログイン一覧、期限一覧、更新ダイアログ
- サービスごとに複数アカウントを束ねる UI
- Chatwork 通知連携

### 9.3 Phase 3

- broker 経由の半自動更新
- 承認ダイアログ
- 更新ワークフローのジョブ化

## 10. CLI への追加要件

既存の `get/set/list/view` だけでは足りないので、将来的に次を追加します。

```text
secrets add api ...
secrets add login ...
secrets rotate begin RECORD_ID
secrets rotate confirm RECORD_ID
secrets revoke RECORD_ID
secrets due list
secrets due notify
secrets audit RECORD_ID
```

`service_name` だけでは一意にならないため、`record_id` と `account_label` を人間に見せる前提にします。

### 10.1 `add login` のイメージ

```bash
$ secrets add login freee-admin \
  --entity-id "C02" \
  --account-label "経理管理者" \
  --usage-purpose "月次締め・支払確認" \
  --login-url "https://accounts.secure.freee.co.jp/" \
  --company-code "C02" \
  --user-code "admin@example.com" \
  --classification P2b \
  --rotation-days 90
Password: ********
Saved: rec_web_001
```

同じサービスで別アカウントを追加する例:

```bash
$ secrets add login freee-admin \
  --entity-id "C02" \
  --account-label "閲覧専用" \
  --usage-purpose "残高確認" \
  --login-url "https://accounts.secure.freee.co.jp/" \
  --company-code "C02" \
  --user-code "viewer@example.com" \
  --classification P2b \
  --rotation-days 90
Password: ********
Saved: rec_web_002
```

### 10.2 更新期限の確認

```bash
$ secrets due list
RECORD_ID      SERVICE        ENTITY  ACCOUNT_LABEL  STATUS         DUE_DATE
rec_web_001    freee-admin    C02     経理管理者     rotation_due   2026-04-09
rec_web_002    freee-admin    C02     閲覧専用       rotation_due   2026-04-10
rec_api_004    notion         C02     本番API        rotation_due   2026-04-12
```

### 10.3 失効

```bash
$ secrets revoke rec_api_004
Reason: token regenerated
Revoked: rec_api_004
```

## 11. 自動化の粒度

### 11.1 自動に向くもの

- API トークンの再取得
- 更新期限の判定
- 通知送信
- 重複候補の検知

### 11.2 半自動に向くもの

- Web サイトのパスワード変更
- 人間のログインを伴う更新
- 重複候補のマージ
- 失効確認

### 11.3 自動にしない方がよいもの

- AI がパスワード本文を勝手に Chatwork へ送ること
- AI が古い値を自動削除すること
- AI が人間用アカウントを無確認で上書きすること

## 12. business-master-sync 連携方針

### 12.1 役割分担

`business-master-sync` は「公開してよい運用メタデータ」の管理台帳、
`credential-vault` は「秘密値そのもの」の保管庫として分けます。

スプシに置いてよいもの:

- サービス名
- 法人ID
- 部門ID
- ログイン URL
- 会社コードの有無
- アカウントラベル
- 用途
- オーナー
- 更新周期
- 状態
- `credential_record_id`

スプシに置かないもの:

- パスワード本文
- API キー全文
- リフレッシュトークン
- 秘密のメモ本文

### 12.2 シート案

既存の `ツール` シートはサービス存在確認には向きますが、アカウント単位には粗いです。
そのため、追加候補として次のシートを想定します。

1. `利用サービス`
2. `サービスアカウント`

`利用サービス` の列例:

- `サービスID`
- `サービス名`
- `カテゴリ`
- `標準ログインURL`
- `備考`

`サービスアカウント` の列例:

- `サービスID`
- `法人ID`
- `部門ID`
- `アカウントラベル`
- `用途`
- `会社コード`
- `ユーザーコード`
- `オーナー`
- `運用モード`
- `更新周期日数`
- `ステータス`
- `credential_record_id`
- `最終確認日`
- `備考`

### 12.3 YAML 同期の考え方

`business_context.yaml` に同期するのは秘密値ではなく、アカウントの存在と参照情報だけにします。

例:

- `service_id`
- `entity_id`
- `account_label`
- `usage_purpose`
- `credential_record_id`
- `status`

これなら AI は「どのサービスにどんなアカウントがあるか」は把握でき、秘密値そのものは引き続き vault からのみ取得します。

### 12.4 人間向けインターフェイスへの効き方

この構成にすると、人間向け UI は次の 2 つを両立できます。

- スプシでサービス・アカウント構成を俯瞰する
- Web アプリや CLI で秘密値だけを安全に参照・更新する

つまり、「同じ freee に複数アカウントがある」ことをスプシで認識しつつ、実パスワードはスプシに置かない運用ができます。

## 13. 実装優先順位の見直し

この2目標を踏まえると、優先順位は次の順が自然です。

1. vault と共通レコードモデルを作る
2. `api_secret` と `web_login` を同じ vault で扱えるようにする
3. `entity_id`、`account_label`、`usage_purpose` を含む複数アカウント前提の識別子を実装する
4. 期限管理と状態管理を実装する
5. `revoke` と `due list` を実装する
6. business-master-sync のシート設計を決めて `credential_record_id` 連携を入れる
7. ローカル Web アプリを載せる
8. Chatwork 通知を追加する
9. broker と暗号化受け渡しを追加する

## 14. この時点での推奨判断

今の段階で先に決めてよいこと:

- vault は「秘密値 + メタデータ + 状態」を持つ台帳にする
- Chatwork は通知だけに使う
- 人間向け UI の本命はローカル Web アプリにする
- 同一サービスの複数アカウントを前提に、`entity_id + account_label` を必須寄りに扱う
- business-master-sync 側には非秘密メタデータだけを置く
- AI 間共有は原則として参照名だけにする
- 失効は削除より `revoke` を基本にする

まだ保留でよいこと:

- Web アプリの技術スタック
- Chatwork 通知の文面細部
- 暗号化バンドルで `age` と独自 envelope のどちらを採るか
- 旧値履歴をどこまで残すか

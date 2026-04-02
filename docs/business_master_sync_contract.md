# business-master-sync 連携案

この文書は、`business-master-sync` の管理スプレッドシートと `credential-vault` をどうつなぐかの具体案です。
目的は、「同一サービスに複数アカウントがある」現実を人間が管理しやすくしつつ、秘密値そのものはスプシへ置かないことです。

## 1. 役割分担

### 1.1 business-master-sync が持つもの

- どの法人がどのサービスを使っているか
- 同じサービスの中でどんなアカウントがあるか
- それぞれの用途、担当者、更新周期、状態
- `credential-vault` 側の `record_id`

### 1.2 credential-vault が持つもの

- パスワード本文
- API キー本文
- リフレッシュトークン
- MFA メモなどの機微情報

## 2. 推奨シート構成

既存の `ツール` シートは「サービスが存在するか」の管理には向いていますが、アカウント単位には粗いです。
そのため、次の 2 シートを追加する想定です。

1. `利用サービス`
2. `サービスアカウント`

## 3. `利用サービス` シート案

### 3.1 用途

- サービス自体のマスタ
- ログイン URL やカテゴリの基準値
- アカウント群の親テーブル

### 3.2 列定義

| 列名 | 必須 | 例 | 説明 |
|---|---|---|---|
| サービスID | 必須 | `SVC_FREEE` | スプシ内の一意キー |
| サービス名 | 必須 | `freee-admin` | `credential-vault` の `service_name` と揃える |
| カテゴリ | 必須 | `saas` | `saas` / `infra` / `ai` 等 |
| 標準ログインURL | 任意 | `https://accounts.secure.freee.co.jp/` | アカウントごとの既定値 |
| 認証種別 | 任意 | `password` | `password` / `api_key` / `oauth` |
| ベンダー | 任意 | `freee` | 提供元 |
| ステータス | 必須 | `active` | `active` / `inactive` |
| 備考 | 任意 |  | 補足 |

## 4. `サービスアカウント` シート案

### 4.1 用途

- 同一サービスの複数アカウント管理
- 法人単位・部門単位の割り当て
- 更新期限や運用モードの確認

### 4.2 列定義

| 列名 | 必須 | 例 | 説明 |
|---|---|---|---|
| アカウントID | 必須 | `ACC_FREEE_C02_ADMIN` | スプシ内の一意キー |
| サービスID | 必須 | `SVC_FREEE` | `利用サービス` への参照 |
| 法人ID | 必須 | `C02` | `法人マスタ` に揃える |
| 部門ID | 任意 | `D01` | 必要時のみ |
| アカウントラベル | 必須 | `経理管理者` | 人間が識別しやすい表示名 |
| 用途 | 必須 | `月次締め・支払確認` | `usage_purpose` |
| ログインURL | 任意 | `https://accounts.secure.freee.co.jp/` | 個別 URL がある場合だけ上書き |
| 会社コード | 任意 | `C02` | サービス固有コード |
| ユーザーコード | 任意 | `admin@example.com` | サービス固有コード |
| ユーザー名 | 任意 | `admin@example.com` | ログイン名 |
| オーナー | 任意 | `Kohei` | 更新責任者 |
| 運用モード | 必須 | `manual` | `manual` / `assisted` / `automatic` |
| 更新周期日数 | 任意 | `90` | `rotation_policy.interval_days` |
| 通知先 | 任意 | `Chatwork` | 将来の通知ルール用 |
| ステータス | 必須 | `active` | `active` / `rotation_due` / `revoked` / `retired` |
| credential_record_id | 任意 | `rec_web_001` | vault 側の record_id |
| 最終確認日 | 任意 | `2026-04-02` | 人間確認日 |
| 備考 | 任意 |  | 秘密値を含めない |

## 5. 運用ルール

### 5.1 スプシに書いてよいもの

- ログイン URL
- 会社コード
- ユーザーコード
- アカウントラベル
- 用途
- 更新周期
- 状態
- record_id

### 5.2 スプシに書かないもの

- パスワード本文
- API キー全文
- アクセストークン
- リフレッシュトークン
- MFA シークレット

## 6. YAML へ同期する項目

`business_context.yaml` に載せるのは、AI が「存在を理解するための情報」だけにします。

```yaml
service_accounts:
  - account_id: "ACC_FREEE_C02_ADMIN"
    service_name: "freee-admin"
    entity_id: "C02"
    department_id: null
    account_label: "経理管理者"
    usage_purpose: "月次締め・支払確認"
    login_url: "https://accounts.secure.freee.co.jp/"
    status: "active"
    credential_record_id: "rec_web_001"
```

この YAML には秘密値を入れません。

## 7. 期待される人間の使い方

1. `business-master-sync` のスプシでサービス構成とアカウント一覧を俯瞰する
2. 更新対象のアカウントを `サービスアカウント` シートで確認する
3. 実際のパスワードや API キーは `credential-vault` で見る
4. 更新後に `credential_record_id` は維持したまま状態や最終確認日を更新する

## 8. 実装時の優先事項

1. `credential-vault` 側で `record_id` を安定生成する
2. `business-master-sync` に `利用サービス` と `サービスアカウント` を追加する
3. `business_context.yaml` に非秘密の `service_accounts` を出す
4. 将来の Web UI はこの `service_accounts` を左ペイン一覧として利用する

# credential-vault - AI作業ガイド

## リポジトリの目的

**P12: クレデンシャル管理基盤**

ID・パスワード・APIキーをNH1上の暗号化vaultで一元管理し、
1Password CLI的なインターフェースで各プロジェクトから安全に取得できるようにする。
人間も `secrets` CLIで追加・参照・更新が可能。

### アーキテクチャ

```
NH1: /home/horizontalhold/auto_project/credential-vault/
├── vault.enc          # 暗号化されたvaultファイル（GitHub非管理）
└── secrets            # CLIエントリポイント

# 使い方
secrets get NOTION_TOKEN       # 値を取得（各プロジェクトから呼び出し）
secrets set NOTION_TOKEN xxx   # 値を登録
secrets list                   # 一覧（値は非表示）
secrets view NOTION_TOKEN      # 値を表示（マスターPW要求）
```

### セキュリティレベル分類

| レベル | 内容 | 例 |
|--------|------|-----|
| P1a | システム情報 | APIエンドポイント、設定値 |
| P1b | プロジェクト情報 | GitHub Token, Notion Token |
| P2a | 個人情報系 | 担当者ログイン情報 |
| P2b | 財務情報系 | freee APIキー, 会計システムPW |
| P3 | 機微情報 | オフライン管理推奨 |

### NH1環境

- 端末: MS-NH1 / Lubuntu 22.04 / RAM 2GB
- ユーザー: horizontalhold
- vault配置先: `/home/horizontalhold/auto_project/credential-vault/`
- **vault.encはGitHub非管理**

---

## 管理元

このリポジトリは **[no-tion-plan](https://github.com/uedasunknowledge-crypto/no-tion-plan)** で横断管理されています。

**このリポジトリで機能・タスクが完了したら、no-tion-planのTASKS.mdに実装状況を反映すること。**

---

## ルール

- **コミットメッセージ**: `feat:` / `fix:` / `docs:` / `refactor:` プレフィックス
- **vault.enc は絶対にコミットしない**（`.gitignore` 対象）
- **マスターパスワードは絶対にコミットしない**
- **`.env` は絶対にコミットしない**
- **データ区分**: P1a〜P3（セキュリティレベル別に管理）

---

## 🤖 AI アシスタントへの指示（必ず読むこと）

### 1. 会話開始時（Resume）

```bash
# ① 最新引継ぎを確認
ls handoff/ 2>/dev/null && cat handoff/$(ls handoff/ | sort | tail -1)

# ② no-tion-plan の TASKS.md でプロジェクト全体状況を確認
cat ../no-tion-plan/TASKS.md 2>/dev/null || echo "GitHubで確認: https://github.com/uedasunknowledge-crypto/no-tion-plan"
```

### 2. 会話終了・中断時（Suspend）

引継ぎファイルを生成すること:
- ファイル名: `handoff/handoff_YYYY-MM-DD_vN.json`
- フォーマット: no-tion-plan の `templates/handoff_v3.json` 参照

### 3. 依存プロジェクト確認

- **P10 nh1-infra** が先行して整備されていることを確認してから着手する
- vault は NH1 上に配置する前提

### 4. セキュリティ最優先

- vault.enc・マスターパスワード・実際の認証情報は絶対にAIに渡さない
- CLIの設計・実装のみAIが担当し、実データの入力は人間が行う

## 言語設定

- 常に日本語で会話する
- コメントも日本語で記述する

# ETC利用照会サービス 明細自動取得ツール

ETC利用照会サービス（https://www.etc-meisai.jp）から毎日明細をダウンロードして、Gmail で送信するツールです。GitHub Actions で毎朝7時（JST）に自動実行されます。

## ファイル構成

```
.
├── scripts/
│   ├── fetch_etc.py     # Playwright でログイン → CSVダウンロード
│   ├── send_mail.py     # Gmail で送信
│   └── main.py          # エントリポイント
├── requirements.txt     # Python 依存パッケージ
├── .env.example         # 環境変数テンプレ（ローカル開発用）
└── .github/workflows/
    └── daily.yml        # 毎朝7時JST 自動実行
```

## セットアップ手順

### 1. GitHub Secrets に認証情報を登録

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** から以下4つを登録：

| Secret 名 | 内容 |
|---|---|
| `ETC_USER_ID` | ETC利用照会サービスのユーザーID |
| `ETC_PASSWORD` | ETC利用照会サービスのパスワード |
| `GMAIL_ADDRESS` | 送信元の Gmail アドレス |
| `GMAIL_APP_PASSWORD` | Gmail のアプリパスワード（後述） |
| `MAIL_TO` | 送信先メールアドレス（カンマ区切りで複数可） |

### 2. Gmail アプリパスワードの取得

1. https://myaccount.google.com/security にアクセス
2. 「2段階認証プロセス」を**有効化**（未設定なら）
3. 「アプリ パスワード」から新しいパスワードを生成
4. 16桁のパスワードを `GMAIL_APP_PASSWORD` に登録

### 3. 手動でテスト実行

GitHub の **Actions** タブから "Daily ETC fetch" ワークフローを選び、**Run workflow** で手動実行できます。

## ローカル開発

```bash
# 依存インストール
pip install -r requirements.txt
playwright install chromium

# 環境変数を設定（.env.example をコピーして編集）
cp .env.example .env
# .env を編集

# 実行
python scripts/main.py
```

## 注意事項

- ETC利用照会サービスは**ログイン失敗を繰り返すとアカウントロック**されます。認証情報は慎重に管理してください。
- 1日1回の実行に留め、サーバーに過度な負荷をかけないでください。
- 利用規約は適宜確認してください。

# ETC利用照会サービス 明細自動取得ツール

ETC利用照会サービス（https://www.etc-meisai.jp）から毎日明細をダウンロードして、**Gmail と LINE** で送信するツールです。GitHub Actions で毎朝7時（JST）に自動実行されます。

## ファイル構成

```
.
├── scripts/
│   ├── fetch_etc.py     # Playwright でログイン → CSVダウンロード
│   ├── send_mail.py     # Gmail で送信（CSV添付）
│   ├── send_line.py     # LINE Messaging API で明細サマリを送信
│   └── main.py          # エントリポイント
├── requirements.txt     # Python 依存パッケージ
├── .env.example         # 環境変数テンプレ（ローカル開発用）
└── .github/workflows/
    └── daily.yml        # 毎朝7時JST 自動実行
```

## セットアップ手順

### 1. GitHub Secrets に認証情報を登録

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** から以下を登録：

| Secret 名 | 内容 |
|---|---|
| `ETC_USER_ID` | ETC利用照会サービスのユーザーID |
| `ETC_PASSWORD` | ETC利用照会サービスのパスワード |
| `GMAIL_ADDRESS` | 送信元の Gmail アドレス |
| `GMAIL_APP_PASSWORD` | Gmail のアプリパスワード（後述） |
| `MAIL_TO` | 送信先メールアドレス（カンマ区切りで複数可） |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API のチャネルアクセストークン |
| `LINE_TO` | LINE の送信先ユーザーID（任意。未設定なら友だち全員へ配信） |

LINE 関連の2つは任意です。未設定の場合は LINE 送信をスキップし、メールのみ送信します。

### 2. Gmail アプリパスワードの取得

1. https://myaccount.google.com/security にアクセス
2. 「2段階認証プロセス」を**有効化**（未設定なら）
3. 「アプリ パスワード」から新しいパスワードを生成
4. 16桁のパスワードを `GMAIL_APP_PASSWORD` に登録

### 3. LINE で受け取れるようにする

LINE 公式アカウントの Messaging API を使って、毎朝の明細サマリを LINE に届けます。

#### 3-1. チャネルアクセストークンを発行

1. [LINE Developers コンソール](https://developers.line.biz/console/) にログイン
2. 対象のチャネル（LINE公式アカウントマネージャーの「Messaging API」画面の **Channel ID** と同じもの）を開く
3. **Messaging API設定** タブ → 一番下の **チャネルアクセストークン（長期）** → 「発行」
4. 発行された文字列を GitHub Secrets の `LINE_CHANNEL_ACCESS_TOKEN` に登録

#### 3-2. 送信先を決める

- **自分だけに届けばよい場合**: LINE公式アカウントを自分の LINE で友だち追加し、`LINE_TO` は**未設定のまま**にします。友だち全員に配信（broadcast）されるため、友だちが自分だけなら実質自分宛てになります。
- **特定の宛先を指定したい場合**: LINE Developers コンソールの **チャネル基本設定** タブにある **あなたのユーザーID**（`U` から始まる文字列）を `LINE_TO` に登録します。グループに送るならグループIDでも構いません。

> Webhook URL の設定は不要です。このツールは受信（Webhook）ではなく送信（push / broadcast）のみを使います。

#### 3-3. 動作確認

```bash
# テキスト1通だけ送ってみる
python scripts/send_line.py

# 手元のCSVから実際のサマリを作って送ってみる
python scripts/send_line.py downloads/example.csv
```

LINE には CSV をそのまま添付できないため、**件数・合計金額・直近20件の明細**をテキストにまとめて送ります。全件は従来どおりメール添付の CSV で確認できます。

### 4. 手動でテスト実行

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
- **チャネルアクセストークンやチャネルシークレットは絶対にリポジトリにコミットしない**でください。画面共有やスクリーンショットで漏れた場合は、LINE Developers コンソールから速やかに再発行してください。
- LINE のブロードキャスト／プッシュ配信は無料プランだと月間の送信数に上限があります（1日1通の運用なら問題ありません）。

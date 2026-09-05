# ETC利用照会サービス 明細自動取得ツール

ETC利用照会サービス（https://www.etc-meisai.jp）から毎日明細をダウンロードして、Gmail で送信するツールです。GitHub Actions で毎朝7時（JST）に自動実行されます。

あわせて、**Claude やコマンドラインから LINE に任意のメッセージを送る**ためのツール（`scripts/line_send.py`）も入っています。

## ファイル構成

```
.
├── scripts/
│   ├── fetch_etc.py     # Playwright でログイン → CSVダウンロード
│   ├── send_mail.py     # Gmail で送信（CSV添付）
│   ├── main.py          # エントリポイント
│   └── line_send.py     # LINE に任意のメッセージを送るCLI（ETC処理とは独立）
├── outbox/
│   └── message.txt      # ここに書いてpushするとLINEに送られる
├── tools/
│   └── gas_line_id_logger.gs  # グループID取得用のGASスクリプト（使い捨て）
├── requirements.txt     # Python 依存パッケージ
├── .env.example         # 環境変数テンプレ（ローカル開発用）
└── .github/workflows/
    ├── daily.yml        # 毎朝7時JST 自動実行（ETC明細）
    ├── line-send.yml    # 手動実行でLINEにメッセージ送信
    └── line-outbox.yml  # outbox/message.txt のpushでLINEに送信
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
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API のチャネルアクセストークン（LINE送信を使う場合のみ） |
| `LINE_TO` | LINE の送信先ユーザーID（任意。未設定なら友だち全員へ配信） |

### 2. Gmail アプリパスワードの取得

1. https://myaccount.google.com/security にアクセス
2. 「2段階認証プロセス」を**有効化**（未設定なら）
3. 「アプリ パスワード」から新しいパスワードを生成
4. 16桁のパスワードを `GMAIL_APP_PASSWORD` に登録

### 3. LINE にメッセージを送れるようにする

`scripts/line_send.py` を使うと、Claude やシェルから LINE 公式アカウント経由で任意のメッセージを送れます。

#### 3-1. チャネルアクセストークンを発行

1. [LINE Developers コンソール](https://developers.line.biz/console/) にログイン
2. 対象のチャネル（LINE公式アカウントマネージャーの「Messaging API」画面の **Channel ID** と同じもの）を開く
3. **Messaging API設定** タブ → 一番下の **チャネルアクセストークン（長期）** → 「発行」
4. 発行された文字列を GitHub Secrets の `LINE_CHANNEL_ACCESS_TOKEN` に登録（ローカルで使うなら `.env` にも）

#### 3-2. 送信先を決める

- **自分だけに届けばよい場合**: LINE公式アカウントを自分の LINE で友だち追加し、`LINE_TO` は**未設定のまま**にします。友だち全員に配信（broadcast）されるため、友だちが自分だけなら実質自分宛てになります。
- **特定の宛先を指定したい場合**: LINE Developers コンソールの **チャネル基本設定** タブにある **あなたのユーザーID**（`U` から始まる文字列）を `LINE_TO` に登録します。グループに送るならグループIDでも構いません。

> Webhook URL の設定は不要です。このツールは受信（Webhook）ではなく送信（push / broadcast）のみを使います。

#### 3-3. 使い方

```bash
# 接続確認（送信はしない。公式アカウント名が表示されれば成功）
python scripts/line_send.py --check

# メッセージを送る
python scripts/line_send.py "17時に出発します"

# 標準入力から送る（コマンドの結果をそのまま流し込める）
git log --oneline -5 | python scripts/line_send.py

# 宛先を指定して送る
python scripts/line_send.py --to Uxxxxxxxxxxxx "特定の相手に送る"

# LINE_TO を無視して友だち全員に送る
python scripts/line_send.py --broadcast "全員へのお知らせ"
```

失敗すると終了コード 1 とエラー内容を返すので、スクリプトから呼んでも成否を判定できます。

#### 3-4. GitHub Actions から送る（手動）

ローカルにトークンを置かずに送りたい場合は、**Actions** タブ → "Send LINE message" → **Run workflow** でメッセージを入力すれば送信できます。

#### 3-5. push で送る（Claude 用）

`outbox/message.txt` を書き換えて push すると、"Send LINE from outbox" ワークフローが自動で起動し、その中身がそのまま LINE に送られます。

```bash
echo "17時に出発します" > outbox/message.txt
git commit -am "LINE送信" && git push
```

Claude は Actions を起動する権限を持たない一方で push はできるため、この経路なら Claude 側の操作だけで LINE に送信できます。ファイルが空のときは送信しません。

### 3-6. グループに送りたい場合

グループへの送信には `LINE_TO` にグループID（`C` で始まる文字列）が必要です。グループIDは Webhook 経由でしか取得できないため、`tools/gas_line_id_logger.gs` を一時的に使って取得します。

1. LINE公式アカウントマネージャー → 設定 → アカウント設定 → 「グループ・複数人トークへの参加を許可する」を有効にする
2. https://script.google.com で新規プロジェクトを作り、`tools/gas_line_id_logger.gs` の内容を貼り付ける
3. 「デプロイ」→「新しいデプロイ」→ ウェブアプリ（実行: 自分 / アクセス: 全員）→ `/exec` のURLをコピー
4. LINE公式アカウントマネージャー → 設定 → 応答設定 → Webhook を有効化し、Messaging API の Webhook URL にそのURLを設定
5. 公式アカウントをグループに招待し、グループ内で何か発言する
6. `/exec` のURLをブラウザで開くと、記録されたIDが表示される
7. 「種別: group」の行のIDを GitHub Secrets の `LINE_TO` に登録する
8. 取得できたら Webhook URL を削除し、GAS のデプロイも削除する

`LINE_TO` を設定すると、以降の送信はすべてその宛先への push になります（友だち全員への broadcast ではなくなります）。

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
- LINE のブロードキャスト／プッシュ配信は無料プランだと月間の送信数に上限があります（無料枠は月200通程度）。

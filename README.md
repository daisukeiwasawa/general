# ETC利用照会サービス 明細自動取得ツール

ETC利用照会サービス（https://www.etc-meisai.jp）から毎日明細をダウンロードして、Gmail で送信するツールです。GitHub Actions で毎朝7時（JST）に自動実行されます。

あわせて次のツールも入っています。

- **イトーキ配送の日次売上計上**（`scripts/itoki_daily.py`）… 代入さまからのメールをもとに、スプレッドシートへの記入と LINE 報告を自動化します。
- **LINE 送信CLI**（`scripts/line_send.py`）… Claude やコマンドラインから LINE に任意のメッセージを送ります。

## ファイル構成

```
.
├── scripts/
│   ├── fetch_etc.py     # Playwright でログイン → CSVダウンロード
│   ├── send_mail.py     # Gmail で送信（CSV添付）
│   ├── main.py          # エントリポイント
│   ├── line_send.py     # LINE に任意のメッセージを送るCLI（ETC処理とは独立）
│   ├── itoki_daily.py   # イトーキ配送の日次売上計上（エントリポイント）
│   └── itoki/
│       ├── mail.py      # 代入さまのメールを IMAP で取得
│       ├── manifest.py  # 配車表PDF → 配送先の読み取り
│       ├── rates.py     # 距離から区分1〜4を判定
│       ├── sheet.py     # スプレッドシート書き込み・シフト表参照
│       ├── notify.py    # LINE 文面の組み立て
│       └── state.py     # 処理済みメールの台帳
├── config/
│   └── itoki_rates.json # 単価表と区分ルール（金額を変えるならここ）
├── apps_script/
│   └── Code.gs          # スプレッドシート側に貼り付けるウェブアプリ
├── state/
│   └── itoki_processed.json  # 処理済みメール（自動更新）
├── outbox/
│   └── message.txt      # ここに書いてpushするとLINEに送られる
├── requirements.txt     # Python 依存パッケージ
├── .env.example         # 環境変数テンプレ（ローカル開発用）
└── .github/workflows/
    ├── daily.yml        # 毎朝7時JST 自動実行（ETC明細）
    ├── itoki-daily.yml  # 毎朝8時JST 自動実行（イトーキ配送の売上計上）
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

---

## イトーキ配送の日次売上計上

代入さま（㈱インフォゲート）から届く業務連絡メールをもとに、毎朝8時（JST）に次を自動で行います。

1. メールを IMAP で取得し、添付の配車表 PDF（F30.pdf）を取り出す
2. 配車表は**スキャン画像でテキストが入っていない**ため、ページを画像に起こして Claude に読ませ、配送日・コース・台数・配送先を構造化データで受け取る
3. プロロジスパーク草加から配送先までの片道距離を測り、お見積りの区分1〜4に当てはめて売上（税抜）を出す
4. スプレッドシート「エレロジ売上」の対象月タブ → `イトーキ配送` → `エレロジ売上（税抜）` に記入
5. シフト表でその日のイトーキ担当ドライバーを調べ、エレロジ日報報告用 LINE でその人にメンションして報告

### 単価の当てはめ方

| 区分 | 条件 | 単価（税抜） |
|---|---|---|
| 1 | 埼玉県・東京都下・北関東（群馬/茨城/栃木）で草加から片道100km圏内 | 32,000円 |
| 2 | 北関東で草加から片道100km以上 | 36,000円 |
| 3 | 長野県の千曲市まで | 43,000円 |
| 4 | 長野県の千曲市以降 | 52,000円 |

- 1便の売上は、その便で**いちばん遠い（単価の高い）配送先**で決めます。台数が2台以上なら台数分を掛けます。
- 距離は Google Maps（`GOOGLE_MAPS_API_KEY` があれば）→ OSRM → 直線距離×1.3 の順に測ります。100km の境界±10km に入ったときは自動計上せず確認を求めます。
- お見積りに載っていない都道府県（千葉・神奈川など）に行った場合も、自動計上せず LINE で手入力をお願いします。
- 時間割増（1時間 3,300円）は配車表から自動判定できないため計上しません。必要なら手で足してください。
- よく行く現場は `config/itoki_rates.json` の `overrides` に住所の一部と区分を登録しておくと、距離計算をせず確実に判定できます。

### セットアップ

#### 1. スプレッドシート側にウェブアプリを置く

Claude や GitHub Actions から Google のセルを直接編集する手段が無いため、シート側に小さなウェブアプリを置いて、そこに書き込みを依頼する形にしています。

1. 「エレロジ売上」のスプレッドシートを開く → **拡張機能 → Apps Script**
2. `apps_script/Code.gs` の中身をそのまま貼り付けて保存
3. 左の歯車（プロジェクトの設定）→ **スクリプト プロパティ** に次を追加
   - `TOKEN` … 好きな長い合言葉（あとで `SHEET_WEBAPP_TOKEN` に同じ値を入れる）
   - `SHIFT_FILE_ID` … シフト表のファイルID（シフト表のURLの `/d/` と `/edit` の間の文字列）
4. シフト表が `.xlsx` 形式のままなら、左メニューの **サービス** ＋ から **Drive API** を追加する（読むときに一時変換するため）
5. **デプロイ → 新しいデプロイ → 種類「ウェブアプリ」**
   - 次のユーザーとして実行: **自分**
   - アクセスできるユーザー: **全員**
6. 出てきた `/exec` で終わる URL を控える（`SHEET_WEBAPP_URL` に入れる）

> コードを直したときは「デプロイを管理」→ 鉛筆アイコン → バージョン「新バージョン」で更新します。URL は変わりません。

#### 2. GitHub Secrets を登録

| Secret 名 | 内容 |
|---|---|
| `ANTHROPIC_API_KEY` | 配車表PDFを読ませるための Claude API キー |
| `ITOKI_IMAP_USER` | 代入さまのメールが届く Gmail アドレス（`daisuke.iwasawa@elelogi.com`） |
| `ITOKI_IMAP_PASSWORD` | 上記アカウントの Gmail アプリパスワード |
| `SHEET_WEBAPP_URL` | 手順1で控えたウェブアプリの URL |
| `SHEET_WEBAPP_TOKEN` | 手順1の `TOKEN` と同じ合言葉 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API のチャネルアクセストークン |
| `LINE_TO` | エレロジ日報報告用 LINE グループのグループID |
| `LINE_MENTION_MAP` | ドライバー名と LINE ユーザーIDの対応（下記） |
| `LINE_MENTION_IDS` | シフト表を引けなかったときの既定のメンション先（カンマ区切り） |
| `GOOGLE_MAPS_API_KEY` | 任意。あれば道のりを正確に測る |

`LINE_MENTION_MAP` はシフト表に書かれている**ドライバー名そのまま**をキーにした JSON です。

```json
{"宮野顕":"Uxxxxxxxx","一瀬修一":"Uyyyyyyyy","岩澤大輔":"Uzzzzzzzz"}
```

現在のシフト表でイトーキを担当しているのは **宮野顕 / 一瀬修一 / 岩澤大輔** の3名です。
ユーザーIDが未登録の人がいる場合はメンションを飛ばし、その旨を本文に書いて送ります。

> メンションは、公式アカウントとその人が**同じグループに参加している**必要があります。

#### 3. 動作確認

**Actions** タブ → "Itoki daily sales" → **Run workflow** で、`dry_run` にチェックを入れて実行すると、
判定結果だけがログに出ます（シート記入も LINE 送信も行いません）。

ローカルで試す場合:

```bash
pip install anthropic
sudo apt-get install -y poppler-utils   # 配車表PDFを画像にするのに必要

python scripts/itoki_daily.py --dry-run              # 判定だけ
python scripts/itoki_daily.py --date 2026-09-07      # 特定の配送日だけ
python scripts/itoki_daily.py --force                # 処理済みメールもやり直す
python scripts/itoki_daily.py --overwrite            # 既に入っている値を上書き
```

### 二重計上の防止

処理したメールの Message-ID を `state/itoki_processed.json` に記録し、次回以降は飛ばします。
また、シートのセルに既に値が入っている場合は上書きせず、その旨を LINE でお知らせします
（上書きしたいときは `--overwrite`、または Actions の手動実行から）。

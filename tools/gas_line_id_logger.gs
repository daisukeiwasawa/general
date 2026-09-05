/**
 * LINE の Webhook を受けて、送信元のID（groupId / roomId / userId）を記録するだけの
 * 使い捨てスクリプト。グループIDは Webhook 経由でしか取得できないため、
 * これを一時的に立てて ID を確認し、確認できたらデプロイを削除する。
 *
 * 使い方:
 *   1. https://script.google.com で新規プロジェクトを作り、この内容を貼り付ける
 *   2. 「デプロイ」→「新しいデプロイ」→ 種類「ウェブアプリ」
 *      - 次のユーザーとして実行: 自分
 *      - アクセスできるユーザー: 全員（LINEからのPOSTを受けるため必須）
 *   3. 発行された /exec のURLを LINE の Webhook URL に設定する
 *   4. 公式アカウントをグループに招待し、グループ内で何か発言する
 *   5. 同じ /exec のURLをブラウザで開くと、記録されたIDが一覧表示される
 */

const PROP_KEY = 'LINE_SOURCES';
const MAX_RECORDS = 20;

/** LINE からの Webhook を受け取る。 */
function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const events = body.events || [];
    const store = PropertiesService.getScriptProperties();
    const records = JSON.parse(store.getProperty(PROP_KEY) || '[]');

    events.forEach(function (event) {
      const source = event.source || {};
      const record = {
        time: new Date().toISOString(),
        eventType: event.type,
        sourceType: source.type || '(不明)',
        groupId: source.groupId || '',
        roomId: source.roomId || '',
        userId: source.userId || '',
      };
      console.log(JSON.stringify(record));
      records.unshift(record);
    });

    store.setProperty(PROP_KEY, JSON.stringify(records.slice(0, MAX_RECORDS)));
  } catch (err) {
    // 受信自体は必ず 200 で返す（LINE 側でエラー扱いにしないため）。
    console.log('受信処理でエラー: ' + err);
  }

  return ContentService.createTextOutput('OK');
}

/** ブラウザでURLを開いたときに、記録したIDを表示する。 */
function doGet() {
  const store = PropertiesService.getScriptProperties();
  const records = JSON.parse(store.getProperty(PROP_KEY) || '[]');

  if (records.length === 0) {
    return ContentService.createTextOutput(
      'まだ受信していません。\n\n' +
        '公式アカウントをグループに招待し、グループ内で何か発言してから、' +
        'このページを再読み込みしてください。'
    );
  }

  const lines = records.map(function (r) {
    const id = r.groupId || r.roomId || r.userId || '(IDなし)';
    return [
      r.time,
      '  種別: ' + r.sourceType + ' / イベント: ' + r.eventType,
      '  ID  : ' + id,
    ].join('\n');
  });

  return ContentService.createTextOutput(
    'グループから届いたものは「種別: group」の行です。\n' +
      'その ID（C で始まる文字列）を LINE_TO に登録してください。\n\n' +
      lines.join('\n\n')
  );
}

/** 記録を消す。取得が終わったら実行しておくとよい。 */
function clearRecords() {
  PropertiesService.getScriptProperties().deleteProperty(PROP_KEY);
  console.log('記録を削除しました。');
}

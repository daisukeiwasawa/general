/**
 * スプレッドシート「エレロジ売上」に外部から売上を書き込むためのウェブアプリ。
 *
 * セットアップ（1回だけ）:
 *   1. 対象のスプレッドシートを開く → 拡張機能 → Apps Script
 *   2. このファイルの中身を貼り付けて保存
 *   3. 左の歯車（プロジェクトの設定）→ スクリプト プロパティ に
 *        TOKEN         = 好きな長い合言葉
 *                        （GitHub Secrets の SHEET_WEBAPP_TOKEN と同じ値にする）
 *        SHIFT_FILE_ID = シフト表のファイルID
 *                        （シフト表のURL /d/ と /edit の間の文字列）
 *      を追加
 *   3-2. シフト表が .xlsx のままの場合は、左メニューの「サービス」＋ から
 *        「Drive API」を追加する（変換して読むために必要）。
 *        シフト表を Google スプレッドシート形式に変換済みなら不要。
 *   4. デプロイ → 新しいデプロイ → 種類「ウェブアプリ」
 *        次のユーザーとして実行: 自分
 *        アクセスできるユーザー: 全員
 *      → デプロイして出てくる /exec で終わる URL を SHEET_WEBAPP_URL に登録
 *
 * コードを直したときは「デプロイを管理」→ 鉛筆アイコン → バージョン「新バージョン」で
 * 更新する（URL は変わらない）。
 */

// 見出しの行番号。row2 = 取引先ブロック名、row3 = 項目名、row4 = 税区分。
var BLOCK_ROW = 2;
var COLUMN_ROW = 3;
var FIRST_DATA_ROW = 5;
var LAST_DATA_ROW = 45;
var MAX_BLOCK_WIDTH = 10;

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    var expected = PropertiesService.getScriptProperties().getProperty('TOKEN');

    if (!expected) {
      return respond({ ok: false, error: 'スクリプト プロパティ TOKEN が未設定です。' });
    }
    if (body.token !== expected) {
      return respond({ ok: false, error: '合言葉が違います。' });
    }

    if (body.action === 'ping') {
      return respond({ ok: true, message: '疎通OK' });
    }
    if (body.action === 'write') {
      return respond(writeSales(body));
    }
    if (body.action === 'shift') {
      return respond(lookupShift(body));
    }
    return respond({ ok: false, error: '不明な action: ' + body.action });
  } catch (err) {
    return respond({ ok: false, error: String(err) });
  }
}

function writeSales(body) {
  var parts = String(body.date).split('-');
  var year = Number(parts[0]);
  var month = Number(parts[1]);
  var day = Number(parts[2]);

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheetName = year + '.' + ('0' + month).slice(-2);
  var sheet = ss.getSheetByName(sheetName) || ss.getSheetByName(year + '.' + month);
  if (!sheet) {
    return { ok: false, error: 'タブ「' + sheetName + '」が見つかりません。' };
  }

  var blockCol = findBlockColumn(sheet, body.block);
  if (!blockCol) {
    return { ok: false, error: 'ブロック「' + body.block + '」が ' + sheetName + ' にありません。' };
  }

  var valueCol = findColumnInBlock(sheet, blockCol, body.column);
  if (!valueCol) {
    return { ok: false, error: '列「' + body.column + '」が ' + body.block + ' ブロックにありません。' };
  }

  var row = findDateRow(sheet, blockCol, year, month, day);
  if (!row) {
    return { ok: false, error: body.date + ' の行が ' + sheetName + ' にありません。' };
  }

  var cell = sheet.getRange(row, valueCol);
  var previous = cell.getValue();
  var occupied = previous !== '' && previous !== null;
  var address = cell.getA1Notation();

  if (occupied && !body.overwrite) {
    return {
      ok: true,
      written: false,
      sheetName: sheetName,
      cell: address,
      previousValue: previous,
      message: '既に ' + previous + ' が入っていたため上書きしませんでした。'
    };
  }

  cell.setValue(body.amount);

  return {
    ok: true,
    written: true,
    sheetName: sheetName,
    cell: address,
    previousValue: occupied ? previous : null,
    message: occupied ? '上書きしました。' : '記入しました。'
  };
}

/** row2 から取引先ブロックの開始列を探す。 */
function findBlockColumn(sheet, name) {
  var values = sheet.getRange(BLOCK_ROW, 1, 1, sheet.getLastColumn()).getValues()[0];
  for (var i = 0; i < values.length; i++) {
    if (String(values[i]).trim() === name) {
      return i + 1;
    }
  }
  return 0;
}

/** ブロックの中（次のブロックが始まるまで）で、row3 が指定名の列を探す。 */
function findColumnInBlock(sheet, blockCol, name) {
  var lastCol = sheet.getLastColumn();
  var width = Math.min(MAX_BLOCK_WIDTH, lastCol - blockCol + 1);
  var blocks = sheet.getRange(BLOCK_ROW, blockCol, 1, width).getValues()[0];
  var headers = sheet.getRange(COLUMN_ROW, blockCol, 1, width).getValues()[0];

  for (var i = 0; i < width; i++) {
    // 隣の取引先ブロックに入ったら打ち切る。
    if (i > 0 && String(blocks[i]).trim() !== '') {
      break;
    }
    if (String(headers[i]).trim() === name) {
      return blockCol + i;
    }
  }
  return 0;
}

/** ブロック先頭列に並ぶ日付から、対象日の行を探す。 */
function findDateRow(sheet, blockCol, year, month, day) {
  var count = LAST_DATA_ROW - FIRST_DATA_ROW + 1;
  var values = sheet.getRange(FIRST_DATA_ROW, blockCol, count, 1).getValues();

  for (var i = 0; i < values.length; i++) {
    var v = values[i][0];
    if (v instanceof Date &&
        v.getFullYear() === year && v.getMonth() + 1 === month && v.getDate() === day) {
      return FIRST_DATA_ROW + i;
    }
  }
  return 0;
}

function respond(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}


/* ------------------------------------------------------------------ *
 * シフト表の参照
 *
 * シフト表の「担当」セクション（A列=担当区分 / B列=ドライバー / 日付列=荷主）
 * から、指定日にその荷主を担当するドライバーを拾う。
 * ------------------------------------------------------------------ */

var SHIFT_DRIVER_COL = 2;   // B列: ドライバー名
var SHIFT_FIRST_COL = 3;    // C列から日付が並ぶ
var SHIFT_MAX_ROWS = 200;

function lookupShift(body) {
  var fileId = PropertiesService.getScriptProperties().getProperty('SHIFT_FILE_ID');
  if (!fileId) {
    return { ok: false, error: 'スクリプト プロパティ SHIFT_FILE_ID が未設定です。' };
  }

  var parts = String(body.date).split('-');
  var year = Number(parts[0]);
  var month = Number(parts[1]);
  var day = Number(parts[2]);
  var client = body.client || 'イトーキ';

  var opened = openShiftSpreadsheet(fileId);
  try {
    var tabName = year + ('0' + month).slice(-2);
    var sheet = opened.ss.getSheetByName(tabName);
    if (!sheet) {
      return { ok: false, error: 'シフト表にタブ「' + tabName + '」がありません。' };
    }

    var header = findAssignmentHeaderRow(sheet);
    if (!header) {
      return { ok: false, error: 'シフト表の「担当 / ドライバー」の見出し行が見つかりません。' };
    }

    var dateCol = findShiftDateColumn(sheet, header - 1, year, month, day);
    if (!dateCol) {
      return { ok: false, error: body.date + ' の列がシフト表にありません。' };
    }

    var drivers = [];
    var lastRow = Math.min(sheet.getLastRow(), header + SHIFT_MAX_ROWS);
    for (var row = header + 1; row <= lastRow; row++) {
      var name = String(sheet.getRange(row, SHIFT_DRIVER_COL).getValue()).trim();
      if (!name) {
        break; // セクションの終わり
      }
      var assignment = String(sheet.getRange(row, dateCol).getValue()).trim();
      if (assignment && assignment.indexOf(client) >= 0) {
        drivers.push({ name: name, assignment: assignment });
      }
    }

    return { ok: true, sheetName: tabName, client: client, drivers: drivers };
  } finally {
    if (opened.tempId) {
      Drive.Files.remove(opened.tempId);
    }
  }
}

/** シフト表を開く。.xlsx のままなら一時的にスプレッドシートへ変換する。 */
function openShiftSpreadsheet(fileId) {
  try {
    return { ss: SpreadsheetApp.openById(fileId), tempId: null };
  } catch (e) {
    var blob = DriveApp.getFileById(fileId).getBlob();
    var created = Drive.Files.create(
      { name: 'itoki-shift-temp-' + Date.now(), mimeType: MimeType.GOOGLE_SHEETS },
      blob
    );
    return { ss: SpreadsheetApp.openById(created.id), tempId: created.id };
  }
}

/** A列が「担当」かつB列が「ドライバー」の見出し行を探す。 */
function findAssignmentHeaderRow(sheet) {
  var lastRow = Math.min(sheet.getLastRow(), SHIFT_MAX_ROWS);
  var values = sheet.getRange(1, 1, lastRow, 2).getValues();
  for (var i = 0; i < values.length; i++) {
    if (String(values[i][0]).trim() === '担当' && String(values[i][1]).trim() === 'ドライバー') {
      return i + 1;
    }
  }
  return 0;
}

/** 見出しの1つ上に並ぶ日付から、対象日の列を探す。 */
function findShiftDateColumn(sheet, dateRow, year, month, day) {
  if (dateRow < 1) {
    return 0;
  }
  var lastCol = sheet.getLastColumn();
  var width = lastCol - SHIFT_FIRST_COL + 1;
  if (width < 1) {
    return 0;
  }
  var values = sheet.getRange(dateRow, SHIFT_FIRST_COL, 1, width).getValues()[0];
  for (var i = 0; i < values.length; i++) {
    var v = values[i];
    if (v instanceof Date &&
        v.getFullYear() === year && v.getMonth() + 1 === month && v.getDate() === day) {
      return SHIFT_FIRST_COL + i;
    }
  }
  return 0;
}

/* ------------------------------------------------------------------ *
 * 動作確認用
 *
 * Apps Script エディタ上部の関数選択でこれらを選び「実行」すると、
 * 設定が正しいかを送信なしで確かめられる（結果は「実行ログ」に出る）。
 * 初回は Google の承認画面が出るので、許可すること。
 * ------------------------------------------------------------------ */

/** 売上シートの書き込み先セルを、書き込まずに確認する。 */
function testFindCell() {
  var today = new Date();
  var date = Utilities.formatDate(today, 'Asia/Tokyo', 'yyyy-MM-dd');

  var props = PropertiesService.getScriptProperties();
  Logger.log('TOKEN 設定済み: ' + (props.getProperty('TOKEN') ? 'はい' : 'いいえ'));
  Logger.log('SHIFT_FILE_ID 設定済み: ' + (props.getProperty('SHIFT_FILE_ID') ? 'はい' : 'いいえ'));

  var parts = date.split('-');
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheetName = parts[0] + '.' + parts[1];
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    Logger.log('タブ「' + sheetName + '」が見つかりません。');
    return;
  }

  var blockCol = findBlockColumn(sheet, 'イトーキ配送');
  var valueCol = blockCol ? findColumnInBlock(sheet, blockCol, 'エレロジ売上') : 0;
  var row = blockCol ? findDateRow(sheet, blockCol, Number(parts[0]), Number(parts[1]), Number(parts[2])) : 0;

  if (!blockCol || !valueCol || !row) {
    Logger.log('見つかりませんでした（ブロック列=' + blockCol + ' 値列=' + valueCol + ' 行=' + row + '）');
    return;
  }
  var cell = sheet.getRange(row, valueCol);
  Logger.log(date + ' の書き込み先: ' + sheetName + ' の ' + cell.getA1Notation() +
             '（現在の値: ' + cell.getValue() + '）');
}

/** シフト表を読めるか、今日のイトーキ担当を引いて確認する。 */
function testShiftLookup() {
  var date = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd');
  var token = PropertiesService.getScriptProperties().getProperty('TOKEN');
  Logger.log(JSON.stringify(lookupShift({ token: token, date: date, client: 'イトーキ' })));
}

"""LINE Messaging API で明細の内容を送信する。

LINE_TO が設定されていれば push（特定の宛先へ）、未設定なら broadcast
（公式アカウントを友だち追加している全員へ）で送る。
LINE_CHANNEL_ACCESS_TOKEN が未設定のときは何もしない（メール送信のみで動く）。
"""

import csv
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

PUSH_URL = "https://api.line.me/v2/bot/message/push"
BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

# LINE の1メッセージあたりの上限は5000文字。余裕を持って切る。
MAX_TEXT_LEN = 4800

# ETC の CSV は Shift_JIS のことが多いが、環境によって異なるので順に試す。
CSV_ENCODINGS = ("cp932", "utf-8-sig", "utf-8")


def _enabled() -> bool:
    return bool(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))


def _post(url: str, payload: dict) -> None:
    token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        res.read()


def send_line_text(text: str) -> None:
    """LINE にテキストを送る。トークン未設定なら黙ってスキップする。"""
    if not _enabled():
        print("LINE_CHANNEL_ACCESS_TOKEN が未設定のため LINE 送信をスキップします。")
        return

    text = text.strip()
    if len(text) > MAX_TEXT_LEN:
        text = text[: MAX_TEXT_LEN - 3] + "..."

    message = {"type": "text", "text": text}
    to = os.environ.get("LINE_TO", "").strip()

    try:
        if to:
            _post(PUSH_URL, {"to": to, "messages": [message]})
        else:
            _post(BROADCAST_URL, {"messages": [message]})
    except urllib.error.HTTPError as e:
        # LINE 送信の失敗でメール送信まで巻き添えにしない。
        body = e.read().decode("utf-8", errors="replace")
        print(f"LINE 送信に失敗しました: {e.code} {body}")
    except Exception as e:  # noqa: BLE001 - ネットワーク周りは何が来ても握る
        print(f"LINE 送信に失敗しました: {e}")


def _read_rows(csv_path: Path) -> list[list[str]]:
    for encoding in CSV_ENCODINGS:
        try:
            with open(csv_path, encoding=encoding, newline="") as f:
                return [row for row in csv.reader(f) if any(c.strip() for c in row)]
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", b"", 0, 1, "文字コードを判別できませんでした")


def _to_amount(value: str) -> int | None:
    """「1,234」「\\1,234円」のような表記を数値にする。数値でなければ None。"""
    cleaned = value.strip().replace(",", "").replace("円", "").replace("\\", "").replace("￥", "")
    if cleaned.lstrip("-").isdigit():
        return int(cleaned)
    return None


def summarize_csv(csv_path: Path, max_rows: int = 20) -> str:
    """CSV を LINE で読める短いテキストにまとめる。"""
    header = f"ETC明細 ({datetime.now():%Y-%m-%d})"

    try:
        rows = _read_rows(csv_path)
    except Exception as e:  # noqa: BLE001 - 中身が読めなくても通知自体は届けたい
        return f"{header}\n明細を取得しましたが、CSVの読み取りに失敗しました: {e}"

    if not rows:
        return f"{header}\n対象期間の利用明細はありませんでした。"

    # 1行目はヘッダ行とみなす（数値だけの行ならデータとして扱う）。
    if any(_to_amount(c) is not None for c in rows[0]):
        data_rows = rows
    else:
        data_rows = rows[1:]

    if not data_rows:
        return f"{header}\n対象期間の利用明細はありませんでした。"

    lines = [header, f"件数: {len(data_rows)}件"]

    # 各行で最も右にある数値列を金額とみなして合計する。
    total = 0
    found_amount = False
    for row in data_rows:
        amounts = [a for a in (_to_amount(c) for c in row) if a is not None]
        if amounts:
            total += amounts[-1]
            found_amount = True
    if found_amount:
        lines.append(f"合計: {total:,}円")

    lines.append("")
    for row in data_rows[:max_rows]:
        lines.append(" / ".join(c.strip() for c in row if c.strip()))
    if len(data_rows) > max_rows:
        lines.append(f"...ほか {len(data_rows) - max_rows}件")

    lines.append("")
    lines.append("※全件はメール添付のCSVをご確認ください。")
    return "\n".join(lines)


def send_line_report(csv_path: Path) -> None:
    """明細CSVの要約を LINE に送る。"""
    send_line_text(summarize_csv(csv_path))


def send_line_error(error_message: str) -> None:
    send_line_text(
        f"[ERROR] ETC明細取得失敗 ({datetime.now():%Y-%m-%d})\n\n{error_message}"
    )


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    load_dotenv()
    if len(sys.argv) > 1:
        send_line_report(Path(sys.argv[1]))
    else:
        send_line_text("ETC明細ツールからのテスト送信です。")

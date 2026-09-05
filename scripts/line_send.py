"""LINE にメッセージを送るための汎用CLI。

Claude やシェルから任意のテキストを LINE に投げるために使う。

    python scripts/line_send.py "帰りに牛乳買ってきて"
    echo "処理が終わりました" | python scripts/line_send.py
    python scripts/line_send.py --to 営業チーム "宛先を名前で指定"
    python scripts/line_send.py --to Cxxxxxxxx "宛先をIDで指定"
    python scripts/line_send.py --check          # 接続確認（送信はしない）
    python scripts/line_send.py --list-targets   # 登録済みの宛先名を表示

本文の先頭に「To: 宛先名」の行を書いて --parse-header を付けると、
その宛先へ送る（outbox 方式で使う）。

必要な環境変数（.env でも可）:
    LINE_CHANNEL_ACCESS_TOKEN  チャネルアクセストークン（必須）
    LINE_TARGETS               宛先の一覧。「名前=ID」を1行に1つ書く
                                   営業チーム=Cxxxxxxxx
                                   自分=Uxxxxxxxx
    LINE_TO                    宛先が指定されなかったときの既定の送信先
                               これも未設定なら友だち全員へ broadcast する

宛先の優先順位:
    本文の To: 行  >  --to  >  LINE_TO  >  broadcast
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

API_BASE = "https://api.line.me/v2/bot"

# LINE の1メッセージあたりの上限は5000文字。
MAX_TEXT_LEN = 5000

# ユーザーID(U)・グループID(C)・複数人トークID(R) は英数字33文字。
ID_PATTERN = re.compile(r"[UCR][0-9a-fA-F]{32}")


class LineError(RuntimeError):
    """LINE API 呼び出しが失敗したことを表す。"""


def _request(path: str, payload: dict | None = None) -> dict:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        raise LineError(
            "LINE_CHANNEL_ACCESS_TOKEN が設定されていません。"
            ".env に書くか環境変数として渡してください。"
        )

    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        headers=headers,
        method="POST" if data is not None else "GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        hint = ""
        if e.code == 401:
            hint = " トークンが無効か期限切れの可能性があります。"
        elif e.code == 403:
            hint = " このチャネルに送信権限がないか、プランの上限に達しています。"
        raise LineError(f"LINE API エラー {e.code}: {detail}{hint}") from e
    except urllib.error.URLError as e:
        raise LineError(f"LINE API に接続できません: {e.reason}") from e

    return json.loads(body) if body.strip() else {}


def load_targets() -> dict[str, str]:
    """LINE_TARGETS を読んで「名前 -> ID」の対応表にする。

    1行に1つ「名前=ID」の形式で書く。空行と # で始まる行は無視する。
    """
    targets: dict[str, str] = {}
    for line in os.environ.get("LINE_TARGETS", "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if name and value:
            targets[name] = value
    return targets


def resolve_destination(value: str | None) -> str:
    """宛先の指定（名前またはID）を、実際に送る先のIDにする。

    LINE_TARGETS に登録された名前ならそのIDへ、IDの形をしていればそのまま使う。
    どちらでもない場合は、打ち間違いを見逃さないようエラーにする。
    """
    value = (value or "").strip()
    if not value:
        return ""

    targets = load_targets()
    if value in targets:
        return targets[value]

    if ID_PATTERN.fullmatch(value):
        return value

    known = "、".join(targets) if targets else "（未登録）"
    raise LineError(
        f"宛先「{value}」が分かりません。"
        f"LINE_TARGETS に登録されている宛先: {known}"
    )


def split_header(text: str) -> tuple[str | None, str]:
    """本文の先頭に「To: 宛先」の行があれば、宛先と本文に分ける。"""
    lines = text.splitlines()
    if lines and lines[0].strip().lower().startswith("to:"):
        destination = lines[0].split(":", 1)[1].strip()
        return destination, "\n".join(lines[1:])
    return None, text


def send_text(text: str, to: str | None = None, broadcast: bool = False) -> str:
    """LINE にテキストを送り、送信方法を説明する文字列を返す。

    to には LINE_TARGETS に登録した名前かIDを渡せる。省略時は環境変数
    LINE_TO を使い、それも無い（または broadcast=True）なら友だち全員へ
    broadcast する。
    """
    text = text.strip()
    if not text:
        raise LineError("送信するテキストが空です。")
    if len(text) > MAX_TEXT_LEN:
        text = text[: MAX_TEXT_LEN - 3] + "..."

    message = {"type": "text", "text": text}
    requested = (to or os.environ.get("LINE_TO", "")).strip()
    destination = "" if broadcast else resolve_destination(requested)

    if destination:
        _request("/message/push", {"to": destination, "messages": [message]})
        # 名前で指定されたときはIDをログに出さない。
        return f"push → {requested}"

    _request("/message/broadcast", {"messages": [message]})
    return "broadcast → 友だち全員"


def check() -> str:
    """トークンが有効かを確認し、公式アカウント名を返す。"""
    info = _request("/info")
    name = info.get("displayName", "(名前不明)")
    return f"{name} (basicId: {info.get('basicId', '-')})"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LINE にメッセージを送る",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("message", nargs="*", help="送信するテキスト（省略時は標準入力）")
    parser.add_argument(
        "--to",
        help="送信先。LINE_TARGETS に登録した名前かID（LINE_TO より優先）",
    )
    parser.add_argument(
        "--broadcast",
        action="store_true",
        help="LINE_TO を無視して友だち全員に送る",
    )
    parser.add_argument(
        "--parse-header",
        action="store_true",
        help="本文の先頭にある「To: 宛先」の行を宛先として扱う",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="送信せずに接続確認だけ行う",
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="LINE_TARGETS に登録された宛先名を表示する",
    )
    args = parser.parse_args()

    # .env があれば読む（未インストールでも動くようにする）。
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    try:
        if args.list_targets:
            targets = load_targets()
            if not targets:
                print("LINE_TARGETS に宛先が登録されていません。")
            else:
                print("登録済みの宛先:")
                for name in targets:
                    print(f"  - {name}")
            return 0

        if args.check:
            print(f"接続OK: {check()}")
            return 0

        text = " ".join(args.message) if args.message else sys.stdin.read()

        to = args.to
        if args.parse_header:
            header_to, text = split_header(text)
            # 本文の To: 行は --to より優先する。
            to = header_to or to

        result = send_text(text, to=to, broadcast=args.broadcast)
        print(f"送信しました ({result})")
        return 0
    except LineError as e:
        print(f"送信に失敗しました: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

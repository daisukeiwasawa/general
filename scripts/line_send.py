"""LINE にメッセージを送るための汎用CLI。

Claude やシェルから任意のテキストを LINE に投げるために使う。

    python scripts/line_send.py "帰りに牛乳買ってきて"
    echo "処理が終わりました" | python scripts/line_send.py
    python scripts/line_send.py --to Uxxxxxxxx "特定の相手に送る"
    python scripts/line_send.py --check      # 接続確認（送信はしない）

    python scripts/line_send.py --mention U1234,U5678 "メンション付きで送る"

必要な環境変数（.env でも可）:
    LINE_CHANNEL_ACCESS_TOKEN  チャネルアクセストークン（必須）
    LINE_TO                    送信先のユーザーID/グループID
                               未設定なら友だち全員へ broadcast する
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = "https://api.line.me/v2/bot"

# LINE の1メッセージあたりの上限は5000文字。
MAX_TEXT_LEN = 5000


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


def build_message(text: str, mentions: list[str] | None = None) -> dict:
    """送信用のメッセージオブジェクトを組み立てる。

    mentions を渡すと textV2 形式にして本文の先頭に実メンションを差し込む。
    "all" を混ぜるとグループ全員へのメンションになる。メンションは相手が
    グループに参加していて、かつ公式アカウントも同じグループにいる必要がある。
    """
    text = text.strip()
    if not text:
        raise LineError("送信するテキストが空です。")

    if not mentions:
        if len(text) > MAX_TEXT_LEN:
            text = text[: MAX_TEXT_LEN - 3] + "..."
        return {"type": "text", "text": text}

    # textV2 では {} がプレースホルダ記号なので、本文からは取り除いておく。
    body = text.replace("{", "［").replace("}", "］")

    substitution = {}
    placeholders = []
    for index, target in enumerate(mentions, start=1):
        key = f"m{index}"
        placeholders.append("{" + key + "}")
        mentionee = (
            {"type": "all"}
            if target.strip().lower() == "all"
            else {"type": "user", "userId": target.strip()}
        )
        substitution[key] = {"type": "mention", "mentionee": mentionee}

    combined = " ".join(placeholders) + "\n" + body
    if len(combined) > MAX_TEXT_LEN:
        combined = combined[: MAX_TEXT_LEN - 3] + "..."

    return {"type": "textV2", "text": combined, "substitution": substitution}


def send_text(
    text: str,
    to: str | None = None,
    broadcast: bool = False,
    mentions: list[str] | None = None,
) -> str:
    """LINE にテキストを送り、送信方法を説明する文字列を返す。

    to を渡せばその宛先へ push。省略時は環境変数 LINE_TO を使い、
    それも無い（または broadcast=True）なら友だち全員へ broadcast する。
    """
    message = build_message(text, mentions)
    destination = None if broadcast else (to or os.environ.get("LINE_TO", "").strip())

    if destination:
        _request("/message/push", {"to": destination, "messages": [message]})
        return f"push → {destination}"

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
    parser.add_argument("--to", help="送信先のユーザーID/グループID（LINE_TO より優先）")
    parser.add_argument(
        "--broadcast",
        action="store_true",
        help="LINE_TO を無視して友だち全員に送る",
    )
    parser.add_argument(
        "--mention",
        help="メンションする相手のユーザーIDをカンマ区切りで指定（all でグループ全員）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="送信せずに接続確認だけ行う",
    )
    args = parser.parse_args()

    # .env があれば読む（未インストールでも動くようにする）。
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    try:
        if args.check:
            print(f"接続OK: {check()}")
            return 0

        text = " ".join(args.message) if args.message else sys.stdin.read()
        mentions = [m for m in (args.mention or "").split(",") if m.strip()]
        result = send_text(text, to=args.to, broadcast=args.broadcast, mentions=mentions)
        print(f"送信しました ({result})")
        return 0
    except LineError as e:
        print(f"送信に失敗しました: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

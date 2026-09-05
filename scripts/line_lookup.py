"""グループID・ユーザーIDから名前を引く。メッセージは送らない。

どのIDがどのグループなのか分からなくなったときに使う。
結果は「名前=ID」の形で出力するので、そのまま LINE_TARGETS に貼れる。

    python scripts/line_lookup.py C1a2b3... C9f8e7...
    python scripts/line_lookup.py < outbox/lookup.txt

必要な環境変数:
    LINE_CHANNEL_ACCESS_TOKEN  チャネルアクセストークン
"""

import sys

from line_send import LineError, _request


def lookup(target_id: str) -> str:
    """IDに対応する名前を返す。取得できなければ理由を返す。"""
    try:
        if target_id.startswith("C"):
            info = _request(f"/group/{target_id}/summary")
            return info.get("groupName") or "(名前なし)"
        if target_id.startswith("U"):
            info = _request(f"/profile/{target_id}")
            return info.get("displayName") or "(名前なし)"
        return "(グループIDでもユーザーIDでもありません)"
    except LineError as e:
        # 1件失敗しても残りは調べたいので、ここで握る。
        return f"(取得できません: {e})"


def read_ids(argv: list[str]) -> list[str]:
    """引数、無ければ標準入力からIDを読む。空行と # の行は無視する。"""
    source = argv if argv else sys.stdin.read().split()
    ids = []
    for token in source:
        token = token.strip()
        if token and not token.startswith("#"):
            ids.append(token)
    return ids


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    ids = read_ids(sys.argv[1:])
    if not ids:
        print("IDが指定されていません。", file=sys.stderr)
        return 1

    print("--- LINE_TARGETS に貼れる形式 ---")
    for target_id in dict.fromkeys(ids):  # 重複を除きつつ順序を保つ
        print(f"{lookup(target_id)}={target_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

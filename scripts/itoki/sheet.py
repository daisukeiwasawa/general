"""スプレッドシート「エレロジ売上」への書き込みと、シフト表の参照。

Google Sheets API を直接叩くのではなく、シート側に置いた Apps Script の
ウェブアプリに POST する。サービスアカウントや Google Cloud の設定が要らず、
シートの所有者権限でそのまま読み書きできるため。ウェブアプリ側は apps_script/Code.gs。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date


class SheetError(RuntimeError):
    """ウェブアプリへの書き込みが失敗したことを表す。"""


@dataclass
class WriteResult:
    written: bool
    sheet_name: str
    cell: str
    previous_value: object
    message: str


def _post(endpoint: str, payload: dict) -> dict:
    """ウェブアプリに JSON を投げて、返ってきた JSON を返す。"""
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as res:
            body = res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise SheetError(f"ウェブアプリがエラーを返しました {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise SheetError(f"ウェブアプリに接続できません: {e.reason}") from e

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        # デプロイ設定が「自分だけ」等になっているとログイン HTML が返ってくる。
        raise SheetError(
            "ウェブアプリから JSON 以外が返りました。デプロイのアクセス権を"
            "「全員」にしているか確認してください。"
        ) from None

    if not data.get("ok"):
        raise SheetError(data.get("error", "原因不明のエラー"))
    return data


def lookup_shift(
    endpoint: str,
    token: str,
    delivery_date: date,
    client: str = "イトーキ",
) -> list[str]:
    """シフト表を見て、その日にその荷主を担当するドライバー名を返す。"""
    data = _post(
        endpoint,
        {"token": token, "action": "shift", "date": delivery_date.isoformat(), "client": client},
    )
    return [d["name"] for d in data.get("drivers", [])]


def write_sales(
    endpoint: str,
    token: str,
    delivery_date: date,
    amount: int,
    *,
    block: str = "イトーキ配送",
    column: str = "エレロジ売上",
    overwrite: bool = False,
) -> WriteResult:
    """対象月タブの「イトーキ配送 / エレロジ売上（税抜）」に金額を書く。

    既に値が入っているセルは overwrite=True でない限り上書きしない。
    """
    data = _post(
        endpoint,
        {
            "token": token,
            "action": "write",
            "date": delivery_date.isoformat(),
            "block": block,
            "column": column,
            "amount": amount,
            "overwrite": overwrite,
        },
    )

    return WriteResult(
        written=bool(data.get("written")),
        sheet_name=data.get("sheetName", ""),
        cell=data.get("cell", ""),
        previous_value=data.get("previousValue"),
        message=data.get("message", ""),
    )

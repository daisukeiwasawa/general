"""エレロジ日報報告用 LINE に流す文面を組み立てる。"""

from __future__ import annotations

from datetime import date

WEEKDAYS = "月火水木金土日"


def format_date(d: date) -> str:
    return f"{d.month}/{d.day}（{WEEKDAYS[d.weekday()]}）"


def yen(amount: int) -> str:
    return f"{amount:,}円"


def _driver_line(drivers: list[str]) -> list[str]:
    return [f"担当（シフト表より）：{'・'.join(drivers)}"] if drivers else []


def _note_lines(notes: list[str]) -> list[str]:
    return ["", "※ " + "\n※ ".join(notes)] if notes else []


def success_message(
    delivery_date: date,
    lines: list[str],
    total: int,
    sheet_name: str,
    cells: list[str],
    drivers: list[str] | None = None,
    notes: list[str] | None = None,
) -> str:
    """計上できたときの文面。"""
    where = "・".join(cells) if cells else "-"
    return "\n".join(
        [
            f"イトーキ配送 {format_date(delivery_date)}分の売上を計上しました。",
            *_driver_line(drivers or []),
            "",
            *lines,
            "",
            f"合計（税抜）：{yen(total)}",
            f"記入先：「{sheet_name}」タブ {where}",
            *_note_lines(notes or []),
        ]
    )


def review_message(
    delivery_date: date | None,
    lines: list[str],
    reasons: list[str],
    drivers: list[str] | None = None,
    notes: list[str] | None = None,
) -> str:
    """自動で判断しきれず、人の確認が要るときの文面。"""
    when = format_date(delivery_date) if delivery_date else "（配送日不明）"
    return "\n".join(
        [
            f"イトーキ配送 {when}分の売上を自動計上できませんでした。手入力をお願いします。",
            *_driver_line(drivers or []),
            "",
            *lines,
            "",
            "確認が必要な理由：",
            *[f"・{r}" for r in reasons],
            *_note_lines(notes or []),
        ]
    )


def skipped_message(
    delivery_date: date,
    cell: str,
    previous: object,
    drivers: list[str] | None = None,
    notes: list[str] | None = None,
) -> str:
    """既に値が入っていて上書きしなかったときの文面。"""
    return "\n".join(
        [
            f"イトーキ配送 {format_date(delivery_date)}分は、既に売上が入っていたため上書きしませんでした。",
            *_driver_line(drivers or []),
            "",
            f"入っていた値：{previous}（{cell}）",
            "変更が必要なら手で直してください。",
            *_note_lines(notes or []),
        ]
    )


def destination_lines(entries: list[tuple[str, str, int | None, int, str]]) -> list[str]:
    """便ごとの明細行。entries は (コース, 配送先, 区分, 金額, 判定理由)。"""
    out: list[str] = []
    for course, destination, tier, amount, reason in entries:
        head = f"・{course}：{destination}" if course else f"・{destination}"
        out.append(head)
        if tier is None:
            out.append(f"　区分：判定できず（{reason}）")
        else:
            out.append(f"　区分{tier} / {yen(amount)}（{reason}）")
    return out

"""イトーキ配送の日次売上を、メールからスプレッドシートと LINE へ流す。

    1. 代入さま（㈱インフォゲート）からの業務連絡メールを IMAP で取得
    2. 添付の配車表 PDF から配送日と配送先を読み取る
    3. プロロジスパーク草加からの距離でお見積りの区分1〜4に当てはめ、売上を出す
    4. スプレッドシート「エレロジ売上」の対象月タブに記入
    5. シフト表でその日のイトーキ担当ドライバーを調べる
    6. エレロジ日報報告用 LINE に、担当者へメンションして報告

使い方:
    python scripts/itoki_daily.py                # 通常実行
    python scripts/itoki_daily.py --dry-run      # 判定だけして書き込み・送信はしない
    python scripts/itoki_daily.py --force        # 処理済みのメールも作り直す
    python scripts/itoki_daily.py --overwrite    # 既に値が入っていても上書きする
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import line_send
from itoki import mail, manifest, notify, rates as rates_mod
from itoki.config import env, load_rates, require
from itoki.sheet import SheetError, lookup_shift, write_sales
from itoki.state import State

DEFAULT_SENDER = "takeshi_dainyu@nexus-infogate.co.jp"
DEFAULT_IMAP_HOST = "imap.gmail.com"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="書き込みも LINE 送信もせず、判定結果だけ表示する")
    parser.add_argument("--force", action="store_true", help="処理済みのメールも改めて処理する")
    parser.add_argument("--overwrite", action="store_true", help="シートに既に値が入っていても上書きする")
    parser.add_argument("--since-days", type=int, default=7, help="何日前までのメールを見るか（既定: 7）")
    parser.add_argument("--date", help="この配送日（YYYY-MM-DD）のメールだけ処理する")
    return parser.parse_args()


def default_mentions() -> list[str]:
    """シフト表を引けなかったときに使う既定のメンション先。"""
    return [m.strip() for m in env("LINE_MENTION_IDS").split(",") if m.strip()]


def resolve_mentions(delivery_date: date | None) -> tuple[list[str], list[str], list[str]]:
    """シフト表を見て、その日のイトーキ担当者のLINEユーザーIDを決める。

    戻り値は (メンションするユーザーID, 担当ドライバー名, 補足メモ)。
    シフト表が引けない・担当が載っていない場合は LINE_MENTION_IDS に退避する。
    """
    try:
        mapping = json.loads(env("LINE_MENTION_MAP", default="{}"))
    except json.JSONDecodeError:
        return default_mentions(), [], ["LINE_MENTION_MAP が JSON として読めませんでした"]

    if delivery_date is None:
        return default_mentions(), [], ["配送日が分からないため既定の宛先にメンションしました"]

    try:
        drivers = lookup_shift(
            require("SHEET_WEBAPP_URL"),
            require("SHEET_WEBAPP_TOKEN"),
            delivery_date,
            env("ITOKI_SHIFT_CLIENT", default="イトーキ"),
        )
    except Exception as e:
        return default_mentions(), [], [f"シフト表を確認できず既定の宛先にメンションしました（{e}）"]

    if not drivers:
        return (
            default_mentions(),
            [],
            ["シフト表にこの日のイトーキ担当が見つからず、既定の宛先にメンションしました"],
        )

    ids: list[str] = []
    notes: list[str] = []
    for name in drivers:
        user_id = str(mapping.get(name, "")).strip()
        if user_id:
            ids.append(user_id)
        else:
            notes.append(f"{name} さんの LINE ユーザーIDが未登録のためメンションできませんでした")

    if not ids:
        ids = default_mentions()

    return ids, drivers, notes


def send_line(text: str, dry_run: bool, mentions: list[str] | None = None) -> None:
    mentions = mentions if mentions is not None else default_mentions()

    if dry_run:
        print("--- LINE（送信しません）---")
        if mentions:
            print(f"[メンション: {', '.join(mentions)}]")
        print(text)
        print("---------------------------")
        return

    result = line_send.send_text(text, mentions=mentions)
    print(f"LINE 送信 ({result})")


def classify_trips(trips: list[manifest.Trip], rates: dict):
    """便ごとに単価を決める。1便の売上は、その便でいちばん単価の高い配送先で決まる。"""
    entries: list[tuple[str, str, int | None, int, str]] = []
    reasons: list[str] = []
    total = 0
    needs_review = False

    for trip in trips:
        classified = [rates_mod.classify(d, rates) for d in trip.destinations]
        if not classified:
            needs_review = True
            reasons.append(f"{trip.course}：配送先を読み取れませんでした")
            continue

        for c in classified:
            if c.needs_review:
                needs_review = True
                reasons.append(f"{c.address}：{c.reason}")

        billed = rates_mod.trip_amount(classified)
        if billed is None:
            needs_review = True
            entries.append((trip.course, "・".join(trip.destinations), None, 0, classified[0].reason))
            continue

        trucks = max(1, int(trip.truck_count or 1))
        amount = billed.amount * trucks
        total += amount

        reason = billed.reason if trucks == 1 else f"{billed.reason} × {trucks}台"
        destination = billed.address
        if len(classified) > 1:
            destination += f"（ほか{len(classified) - 1}件、最も遠い先で算定）"

        entries.append((trip.course, destination, billed.tier, amount, reason))

    return entries, total, needs_review, reasons


def process(item: mail.MailItem, rates: dict, args: argparse.Namespace) -> str:
    """メール1通を処理し、記録用のステータス文字列を返す。"""
    pdfs = item.pdf_attachments
    if not pdfs:
        print(f"  添付 PDF が無いため飛ばします: {item.subject}")
        return "no_attachment"

    trips: list[manifest.Trip] = []
    uncertain = False
    notes: list[str] = []
    parsed_date: date | None = None

    for name, data in pdfs:
        print(f"  配車表を読み取り中: {name}")
        result = manifest.extract(data)
        trips.extend(result.trips)
        uncertain = uncertain or result.uncertain
        if result.notes:
            notes.append(result.notes)
        if result.delivery_date and parsed_date is None:
            try:
                parsed_date = datetime.strptime(result.delivery_date, "%Y-%m-%d").date()
            except ValueError:
                pass

    delivery_date = parsed_date or item.delivery_date
    entries, total, needs_review, reasons = classify_trips(trips, rates)
    lines = notify.destination_lines(entries)
    mentions, drivers, mention_notes = resolve_mentions(delivery_date)
    if drivers:
        print(f"  シフト表の担当: {'・'.join(drivers)}")

    if uncertain:
        needs_review = True
        reasons.extend(notes or ["配車表の読み取りに確信が持てませんでした"])
    if delivery_date is None:
        needs_review = True
        reasons.append("配送日を特定できませんでした")

    for line in lines:
        print(f"  {line}")
    print(f"  合計（税抜）: {total:,}円")

    if needs_review:
        send_line(
            notify.review_message(delivery_date, lines, reasons, drivers, mention_notes),
            args.dry_run,
            mentions,
        )
        return "needs_review"

    assert delivery_date is not None
    if args.dry_run:
        send_line(
            notify.success_message(
                delivery_date, lines, total, f"{delivery_date:%Y.%m}", ["(dry-run)"],
                drivers, mention_notes,
            ),
            True,
            mentions,
        )
        return "dry_run"

    try:
        written = write_sales(
            require("SHEET_WEBAPP_URL"),
            require("SHEET_WEBAPP_TOKEN"),
            delivery_date,
            total,
            overwrite=args.overwrite,
        )
    except SheetError as e:
        send_line(
            notify.review_message(
                delivery_date, lines, [f"シートに書き込めませんでした: {e}"], drivers, mention_notes
            ),
            False,
            mentions,
        )
        return "sheet_error"

    if not written.written:
        send_line(
            notify.skipped_message(
                delivery_date, written.cell, written.previous_value, drivers, mention_notes
            ),
            False,
            mentions,
        )
        return "already_filled"

    send_line(
        notify.success_message(
            delivery_date, lines, total, written.sheet_name, [written.cell], drivers, mention_notes
        ),
        False,
        mentions,
    )
    return "written"


def main() -> int:
    args = parse_args()
    rates = load_rates()
    state = State()

    items = mail.fetch_recent(
        host=env("ITOKI_IMAP_HOST", default=DEFAULT_IMAP_HOST),
        user=require("ITOKI_IMAP_USER", "GMAIL_ADDRESS"),
        password=require("ITOKI_IMAP_PASSWORD", "GMAIL_APP_PASSWORD"),
        sender=env("ITOKI_MAIL_SENDER", default=DEFAULT_SENDER),
        since_days=args.since_days,
    )
    print(f"{len(items)} 件のメールが対象期間に見つかりました。")

    only = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    processed = 0

    for item in items:
        if only and item.delivery_date != only:
            continue
        if state.seen(item.message_id) and not args.force:
            continue

        print(f"\n■ {item.subject}（{item.received_at:%Y-%m-%d %H:%M}）")
        try:
            status = process(item, rates, args)
        except Exception as e:  # 1通の失敗で残りを止めない
            print(f"  処理に失敗しました: {e}", file=sys.stderr)
            status = f"error: {e}"
            try:
                send_line(
                    notify.review_message(item.delivery_date, [], [f"処理中にエラーが発生しました: {e}"]),
                    args.dry_run,
                )
            except Exception:
                pass

        processed += 1
        if not args.dry_run:
            state.record(
                item.message_id,
                subject=item.subject,
                delivery_date=item.delivery_date.isoformat() if item.delivery_date else None,
                status=status,
            )

    if not args.dry_run:
        state.save()

    if processed == 0:
        print("新しく処理するメールはありませんでした。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

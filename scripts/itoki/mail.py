"""代入さま（㈱インフォゲート）からの業務連絡メールを IMAP で取ってくる。

Gmail に IMAP でつなぎ、差出人と受信日で絞り込んで、添付の配車表 PDF を取り出す。
件名（例「９月７日（月） 業務」）から配送日を読み取る。
"""

from __future__ import annotations

import email
import imaplib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message

JST = timezone(timedelta(hours=9))

# 件名から「9月7日」を拾う。全角数字は事前に半角へ寄せる。
_SUBJECT_DATE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")


@dataclass
class MailItem:
    """処理対象のメール1通。"""

    message_id: str
    subject: str
    sender: str
    received_at: datetime
    delivery_date: date | None
    attachments: list[tuple[str, bytes]] = field(default_factory=list)

    @property
    def pdf_attachments(self) -> list[tuple[str, bytes]]:
        return [(n, d) for n, d in self.attachments if n.lower().endswith(".pdf")]


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def parse_delivery_date(subject: str, received_at: datetime) -> date | None:
    """件名の「９月７日（月）」から配送日を組み立てる。

    件名に年は入らないので、受信日を基準に年をあてる。
    受信月より大きく戻る月（12月→1月のような年またぎ）は翌年とみなす。
    """
    normalized = unicodedata.normalize("NFKC", subject)
    m = _SUBJECT_DATE.search(normalized)
    if not m:
        return None

    month, day = int(m.group(1)), int(m.group(2))
    year = received_at.year
    if month < received_at.month - 6:
        year += 1
    elif month > received_at.month + 6:
        year -= 1

    try:
        return date(year, month, day)
    except ValueError:
        return None


def _attachments(msg: Message) -> list[tuple[str, bytes]]:
    found: list[tuple[str, bytes]] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = _decode(part.get_filename())
        if not filename:
            continue
        payload = part.get_payload(decode=True)
        if payload:
            found.append((filename, payload))
    return found


def fetch_recent(
    host: str,
    user: str,
    password: str,
    sender: str,
    since_days: int = 7,
    mailbox: str = "INBOX",
) -> list[MailItem]:
    """差出人と期間で絞ってメールを取得し、古い順に返す。"""
    since = (datetime.now(JST) - timedelta(days=since_days)).strftime("%d-%b-%Y")
    items: list[MailItem] = []

    with imaplib.IMAP4_SSL(host) as imap:
        imap.login(user, password)
        imap.select(mailbox, readonly=True)

        # 「送信者アドレスの完全一致」ではなくドメイン一致でも拾えるよう部分一致で検索する。
        status, data = imap.search(None, "FROM", f'"{sender}"', "SINCE", since)
        if status != "OK":
            raise RuntimeError(f"IMAP 検索に失敗しました: {status}")

        for num in data[0].split():
            status, raw = imap.fetch(num, "(RFC822)")
            if status != "OK" or not raw or not isinstance(raw[0], tuple):
                continue

            msg = email.message_from_bytes(raw[0][1])
            received_at = _received_at(msg)
            subject = _decode(msg.get("Subject"))

            items.append(
                MailItem(
                    message_id=(msg.get("Message-ID") or f"uid-{num.decode()}").strip(),
                    subject=subject,
                    sender=_decode(msg.get("From")),
                    received_at=received_at,
                    delivery_date=parse_delivery_date(subject, received_at),
                    attachments=_attachments(msg),
                )
            )

    items.sort(key=lambda i: i.received_at)
    return items


def _received_at(msg: Message) -> datetime:
    parsed = email.utils.parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
    if parsed is None:
        return datetime.now(JST)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)

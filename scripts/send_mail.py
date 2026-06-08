"""Gmail SMTP で明細CSVを添付してメール送信する。"""

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime


def send_mail(
    attachment_path: Path | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> None:
    sender = os.environ["GMAIL_ADDRESS"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]
    recipients = [addr.strip() for addr in os.environ["MAIL_TO"].split(",")]

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject or f"ETC明細 ({datetime.now():%Y-%m-%d})"
    msg.set_content(body or "本日のETC利用明細を添付します。")

    if attachment_path and attachment_path.exists():
        with open(attachment_path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype="text",
                subtype="csv",
                filename=attachment_path.name,
            )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(msg)


def send_error_mail(error_message: str) -> None:
    send_mail(
        subject=f"[ERROR] ETC明細取得失敗 ({datetime.now():%Y-%m-%d})",
        body=f"ETC明細の取得に失敗しました。\n\n{error_message}",
    )

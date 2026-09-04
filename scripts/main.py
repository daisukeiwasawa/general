"""エントリポイント: 明細取得→メール送信＋LINE送信。失敗時はエラー通知を送る。"""

import sys
import traceback
from dotenv import load_dotenv

from fetch_etc import fetch_etc_csv
from send_mail import send_mail, send_error_mail
from send_line import send_line_report, send_line_error


def main() -> int:
    load_dotenv()

    try:
        csv_path = fetch_etc_csv()
    except Exception:
        error = traceback.format_exc()
        send_error_mail(error)
        send_line_error(error)
        return 1

    send_mail(attachment_path=csv_path)
    send_line_report(csv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

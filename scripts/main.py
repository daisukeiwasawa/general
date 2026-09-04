"""エントリポイント: 明細取得→メール送信。失敗時はエラーメールを送る。"""

import sys
import traceback
from dotenv import load_dotenv

from fetch_etc import fetch_etc_csv
from send_mail import send_mail, send_error_mail


def main() -> int:
    load_dotenv()

    try:
        csv_path = fetch_etc_csv()
    except Exception:
        send_error_mail(traceback.format_exc())
        return 1

    send_mail(attachment_path=csv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

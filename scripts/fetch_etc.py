"""
ETC利用照会サービスにログインして明細CSVをダウンロードする。

TODO: 実際のサイトのHTML構造に合わせてセレクタを調整する必要がある。
ログイン画面・明細画面・ダウンロードボタンの実物を見ながら、
TODO とコメントされた箇所を埋めていく。
"""

import os
from pathlib import Path
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www2.etc-meisai.jp/etc/R?funccode=1013000000&nextfunc=1013000000"
DOWNLOAD_DIR = Path(__file__).parent.parent / "downloads"


def fetch_etc_csv() -> Path:
    """ログインしてCSVをダウンロードし、保存先のパスを返す。"""
    user_id = os.environ["ETC_USER_ID"]
    password = os.environ["ETC_PASSWORD"]

    DOWNLOAD_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        page.goto(LOGIN_URL)

        # TODO: ログインフォームのセレクタを実物に合わせる
        page.fill('input[name="userId"]', user_id)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')

        page.wait_for_load_state("networkidle")

        # TODO: 明細ページへの遷移を実装
        # page.click('text=利用明細')

        # TODO: CSVダウンロードボタンをクリック
        with page.expect_download() as download_info:
            page.click('text=CSVダウンロード')  # TODO: 実物に合わせて修正
        download = download_info.value

        save_path = DOWNLOAD_DIR / download.suggested_filename
        download.save_as(save_path)

        browser.close()
        return save_path


if __name__ == "__main__":
    path = fetch_etc_csv()
    print(f"Downloaded: {path}")

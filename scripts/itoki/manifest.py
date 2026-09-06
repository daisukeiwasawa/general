"""配車表 PDF（F30.pdf）から配送先を読み取る。

添付の配車表はスキャン画像でテキスト層が無いため、ページを画像に起こして
Claude に読ませ、構造化 JSON で受け取る。読み取りに自信が無い場合は
`uncertain` を立てさせ、呼び出し側が自動計上を止められるようにしている。
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import anthropic

MODEL = "claude-opus-5"

# Claude API は長辺 1568px を超える画像を内部で縮小するため、最初からその幅で起こす。
RENDER_LONG_EDGE = 1568

SYSTEM = """あなたは物流会社の配車表（車別荷揃表）を読み取る担当者です。
渡された画像は㈱インフォゲートがイトーキ東京ロジスティクスセンターから発行した配車表のスキャンです。
書かれている内容だけを根拠に、指示されたJSONを返してください。推測で住所を補うときは必ずその旨をnotesに書き、
少しでも判断に迷う点があれば uncertain を true にしてください。"""

PROMPT = """この配車表から次を読み取ってください。

1. 配送日（用紙左上の「YYYY/MM/DD」）
2. 便（コース）ごとの情報
   - コース番号（例「233-F30」）
   - 台数（「N 台」の表記）
   - 配送先。用紙中央の列に書かれた届け先の住所・事業所名です。
     都道府県が省略されている場合は市区町村名から補い、補ったことを notes に書いてください。
   - 納品時間帯（例「9:00-12:00」）。読み取れなければ空文字。

同じコース番号・同じ配送日のページが複数枚にわたる場合は、ひとつの便としてまとめ、
配送先だけを重複なく列挙してください。

destinations の各要素は「東京都府中市東芝町1 東芝府中事業所」のように
都道府県から始まる1行の文字列にしてください。

読み取れない項目がある、字がつぶれている、複数の解釈があり得る場合は uncertain を true にし、
何に迷ったかを notes に日本語で書いてください。"""

SCHEMA = {
    "type": "object",
    "properties": {
        "delivery_date": {
            "type": "string",
            "description": "配送日。YYYY-MM-DD 形式。読み取れなければ空文字。",
        },
        "trips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "course": {"type": "string"},
                    "truck_count": {"type": "integer"},
                    "destinations": {"type": "array", "items": {"type": "string"}},
                    "time_window": {"type": "string"},
                },
                "required": ["course", "truck_count", "destinations", "time_window"],
                "additionalProperties": False,
            },
        },
        "uncertain": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "required": ["delivery_date", "trips", "uncertain", "notes"],
    "additionalProperties": False,
}


@dataclass
class Trip:
    course: str
    truck_count: int
    destinations: list[str]
    time_window: str


@dataclass
class Manifest:
    delivery_date: str
    trips: list[Trip]
    uncertain: bool
    notes: str


def render_pages(pdf_bytes: bytes, workdir: Path) -> list[Path]:
    """PDF を 1 ページ 1 枚の PNG に起こす（poppler-utils の pdftoppm を使う）。"""
    if not shutil.which("pdftoppm"):
        raise RuntimeError(
            "pdftoppm が見つかりません。poppler-utils をインストールしてください"
            "（Ubuntu: sudo apt-get install -y poppler-utils）。"
        )

    pdf_path = workdir / "manifest.pdf"
    pdf_path.write_bytes(pdf_bytes)

    subprocess.run(
        [
            "pdftoppm", "-png", "-scale-to", str(RENDER_LONG_EDGE),
            str(pdf_path), str(workdir / "page"),
        ],
        check=True,
        capture_output=True,
    )
    return sorted(workdir.glob("page-*.png"))


def extract(pdf_bytes: bytes, client: anthropic.Anthropic | None = None) -> Manifest:
    """配車表 PDF から配送日・便・配送先を読み取る。"""
    client = client or anthropic.Anthropic()

    with tempfile.TemporaryDirectory() as tmp:
        pages = render_pages(pdf_bytes, Path(tmp))
        if not pages:
            raise RuntimeError("PDF からページ画像を生成できませんでした。")

        content: list[dict] = []
        for page in pages:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.standard_b64encode(page.read_bytes()).decode("ascii"),
                    },
                }
            )
        content.append({"type": "text", "text": PROMPT})

        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": content}],
        )

    if response.stop_reason == "refusal":
        raise RuntimeError("配車表の読み取りがモデルに拒否されました。")

    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    return Manifest(
        delivery_date=data["delivery_date"],
        trips=[Trip(**t) for t in data["trips"]],
        uncertain=bool(data["uncertain"]),
        notes=data["notes"],
    )

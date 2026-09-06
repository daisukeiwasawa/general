"""配送先の住所から、お見積りの区分1〜4を判定して売上を出す。

判定の優先順位:
  1. overrides（住所の部分一致）        … よく行く現場を固定できる
  2. always_review_prefectures          … 見積に無い県は自動計上しない
  3. prefecture_rules                   … 埼玉/東京=区分1、北関東=距離、長野=千曲市基準
自信が持てない場合は needs_review を立て、呼び出し側で計上を止める。
"""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass

PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

GSI_GEOCODE = "https://msearch.gsi.go.jp/address-search/AddressSearch"
OSRM_ROUTE = "https://router.project-osrm.org/route/v1/driving"
GOOGLE_MATRIX = "https://maps.googleapis.com/maps/api/distancematrix/json"

# 直線距離から道のりを見積もるときの係数。関東平野の高速道路利用を想定した実用値。
ROAD_FACTOR = 1.3

_UA = {"User-Agent": "elelogi-itoki-daily/1.0"}


@dataclass
class Classified:
    """配送先1件の判定結果。"""

    address: str
    prefecture: str
    tier: int | None
    amount: int
    label: str
    reason: str
    distance_km: float | None
    needs_review: bool


def _get_json(url: str) -> object:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def detect_prefecture(address: str) -> str:
    for pref in PREFECTURES:
        if pref in address:
            return pref
    return ""


def geocode(address: str) -> tuple[float, float] | None:
    """国土地理院のジオコーディング API で緯度経度を引く（APIキー不要）。"""
    try:
        url = f"{GSI_GEOCODE}?q={urllib.parse.quote(address)}"
        results = _get_json(url)
    except Exception:
        return None

    if not isinstance(results, list) or not results:
        return None
    coords = results[0].get("geometry", {}).get("coordinates")
    if not coords or len(coords) < 2:
        return None
    return float(coords[1]), float(coords[0])  # GeoJSON は [経度, 緯度]


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _google_distance_km(origin: str, destination: str, key: str) -> float | None:
    params = urllib.parse.urlencode(
        {
            "origins": origin,
            "destinations": destination,
            "mode": "driving",
            "language": "ja",
            "region": "jp",
            "key": key,
        }
    )
    try:
        data = _get_json(f"{GOOGLE_MATRIX}?{params}")
        element = data["rows"][0]["elements"][0]
        if element.get("status") != "OK":
            return None
        return element["distance"]["value"] / 1000.0
    except Exception:
        return None


def _osrm_distance_km(origin: tuple[float, float], dest: tuple[float, float]) -> float | None:
    path = f"{origin[1]},{origin[0]};{dest[1]},{dest[0]}"
    try:
        data = _get_json(f"{OSRM_ROUTE}/{path}?overview=false")
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        return data["routes"][0]["distance"] / 1000.0
    except Exception:
        return None


def one_way_distance_km(origin: dict, address: str) -> tuple[float | None, str]:
    """草加から配送先までの片道の道のりを km で返す。

    Google Maps → OSRM → 直線距離×係数 の順に試し、どれで出したかも返す。
    """
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if key:
        km = _google_distance_km(origin["address"], address, key)
        if km is not None:
            return km, "Google Maps の道のり"

    dest = geocode(address)
    if dest is None:
        return None, "住所の位置を特定できず"

    origin_pt = (float(origin["lat"]), float(origin["lon"]))
    km = _osrm_distance_km(origin_pt, dest)
    if km is not None:
        return km, "OSRM の道のり"

    return haversine_km(origin_pt, dest) * ROAD_FACTOR, f"直線距離×{ROAD_FACTOR}の概算"


def _tier(rates: dict, tier: int) -> tuple[int, str]:
    entry = rates["tiers"][str(tier)]
    return int(entry["amount"]), entry["label"]


def classify(address: str, rates: dict) -> Classified:
    """配送先1件を区分1〜4に当てはめる。"""
    prefecture = detect_prefecture(address)

    for fragment, tier in rates.get("overrides", {}).items():
        if fragment in address:
            amount, label = _tier(rates, int(tier))
            return Classified(address, prefecture, int(tier), amount, label,
                              f"登録済みの配送先「{fragment}」に一致", None, False)

    if prefecture in rates.get("always_review_prefectures", []):
        return Classified(address, prefecture, None, 0, "",
                          f"{prefecture}はお見積りの区分1〜4に無いため要確認", None, True)

    rule = rates["prefecture_rules"].get(prefecture)

    if rule == "tier1":
        amount, label = _tier(rates, 1)
        return Classified(address, prefecture, 1, amount, label,
                          f"{prefecture}は区分1", None, False)

    if rule == "nagano":
        for city in rates["nagano_upto_chikuma"]:
            if city in address:
                amount, label = _tier(rates, 3)
                return Classified(address, prefecture, 3, amount, label,
                                  f"{city}は千曲市までの範囲", None, False)
        amount, label = _tier(rates, 4)
        return Classified(address, prefecture, 4, amount, label,
                          "長野県で千曲市までの範囲に該当せず、千曲市以降と判断", None, True)

    if rule == "by_distance":
        km, source = one_way_distance_km(rates["origin"], address)
        if km is None:
            return Classified(address, prefecture, None, 0, "",
                              f"{prefecture}だが距離を測れず（{source}）", None, True)

        threshold = float(rates["distance_threshold_km"])
        band = threshold * float(rates.get("_distance_review_band_pct", 10)) / 100.0
        tier = 1 if km < threshold else 2
        amount, label = _tier(rates, tier)
        borderline = abs(km - threshold) <= band
        reason = f"片道 約{km:.0f}km（{source}）→ 区分{tier}"
        if borderline:
            reason += f"。{threshold:.0f}km の境界に近いため要確認"
        return Classified(address, prefecture, tier, amount, label, reason, km, borderline)

    reason = (
        f"{prefecture}はお見積りの区分1〜4に無いため要確認"
        if prefecture
        else "住所から都道府県を判別できず、区分を決められません"
    )
    return Classified(address, prefecture, None, 0, "", reason, None, True)


def trip_amount(destinations: list[Classified]) -> Classified | None:
    """1便あたりの売上は、その便でいちばん遠い（単価の高い）配送先で決まる。"""
    priced = [d for d in destinations if d.tier is not None]
    if not priced:
        return None
    return max(priced, key=lambda d: d.amount)

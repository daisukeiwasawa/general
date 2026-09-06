"""設定ファイルと環境変数の読み込み。"""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "itoki_rates.json"


def load_rates(path: str | Path | None = None) -> dict:
    """単価表・区分ルールを読む。"""
    return json.loads(Path(path or DEFAULT_CONFIG).read_text(encoding="utf-8"))


def env(name: str, *fallbacks: str, default: str = "") -> str:
    """環境変数を順に見て、最初に値が入っているものを返す。"""
    for key in (name, *fallbacks):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return default


def require(name: str, *fallbacks: str) -> str:
    value = env(name, *fallbacks)
    if not value:
        names = " / ".join((name, *fallbacks))
        raise RuntimeError(f"環境変数 {names} が設定されていません。")
    return value

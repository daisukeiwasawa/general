"""処理済みメールの記録。同じメールで二重に計上しないための台帳。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import REPO_ROOT

DEFAULT_PATH = REPO_ROOT / "state" / "itoki_processed.json"


class State:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or DEFAULT_PATH)
        self.data: dict[str, dict] = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.data = {}

    def seen(self, message_id: str) -> bool:
        return message_id in self.data

    def record(self, message_id: str, **fields) -> None:
        self.data[message_id] = {
            "processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **fields,
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

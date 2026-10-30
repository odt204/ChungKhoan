"""Cấu hình chung: đường dẫn, múi giờ VN, đọc config.yaml."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OHLCV_DIR = DATA_DIR / "ohlcv"
FUNDAMENTALS_DIR = DATA_DIR / "fundamentals"

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def now_vn() -> datetime:
    return datetime.now(TZ)


def load_config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)

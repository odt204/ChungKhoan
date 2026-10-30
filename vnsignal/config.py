"""Cấu hình chung: đường dẫn, múi giờ VN, đọc config.yaml, vốn từ env."""

import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OHLCV_DIR = DATA_DIR / "ohlcv"
FUNDAMENTALS_DIR = DATA_DIR / "fundamentals"
SIGNALS_DIR = DATA_DIR / "signals"
NEWS_DIR = DATA_DIR / "news"
ALERT_STATE_FILE = DATA_DIR / "alert_state.json"
REPORTS_DIR = ROOT / "reports"

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DEFAULT_CAPITAL_VND = 100_000_000


def capital_vnd() -> int:
    """Vốn từ env CAPITAL_VND (không bao giờ log giá trị). Thiếu/sai → mặc định."""
    raw = os.environ.get("CAPITAL_VND", "").strip().replace("_", "").replace(",", "").replace(".", "")
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    logging.getLogger("vnsignal").warning("CAPITAL_VND thiếu hoặc không hợp lệ → dùng vốn mặc định")
    return DEFAULT_CAPITAL_VND


def now_vn() -> datetime:
    return datetime.now(TZ)


def load_config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)

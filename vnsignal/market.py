"""Quy tắc giao dịch thị trường VN: phiên, biên độ, phí/thuế, lô."""

import math
from datetime import datetime, time, timedelta

import pandas as pd

# Phiên đứng giá (high == low) có mức thay đổi cách biên độ không quá ngưỡng này
# được coi là "trắng bên bán" (trần) / "trắng bên mua" (sàn) → không khớp được.
LOCK_TOLERANCE = 0.005


def price_band(ref: float, limit: float) -> tuple[float, float]:
    """(giá sàn, giá trần) theo giá tham chiếu và biên độ."""
    return ref * (1 - limit), ref * (1 + limit)


def lock_state(high: float, low: float, close: float, ref: float, limit: float) -> str | None:
    """'up' nếu cả phiên khóa trần (không mua được), 'down' nếu khóa sàn (không bán được)."""
    if high != low or ref <= 0:
        return None
    change = close / ref - 1
    if change >= limit - LOCK_TOLERANCE:
        return "up"
    if change <= -(limit - LOCK_TOLERANCE):
        return "down"
    return None


def round_lot(shares: float, lot: int) -> int:
    return int(math.floor(shares / lot)) * lot


def buy_cost(shares: int, price: float, trading: dict) -> float:
    return shares * price * (1 + trading["buy_fee"])


def sell_proceeds(shares: int, price: float, trading: dict) -> float:
    return shares * price * (1 - trading["sell_fee"] - trading["sell_tax"])


def drop_unfinished_bars(df: pd.DataFrame, close: str, buffer_minutes: int, now: datetime) -> pd.DataFrame:
    """Bỏ nến của phiên chưa đóng: ngày tương lai, hoặc ngày hôm nay khi `now`
    (giờ VN) chưa qua giờ đóng cửa `close` ("HH:MM") + buffer."""
    today = now.date().isoformat()
    hh, mm = map(int, close.split(":"))
    cutoff = datetime.combine(now.date(), time(hh, mm), tzinfo=now.tzinfo) + timedelta(minutes=buffer_minutes)
    last_allowed = today if now >= cutoff else None
    keep = df["date"] < today
    if last_allowed:
        keep |= df["date"] == last_allowed
    return df[keep].reset_index(drop=True)

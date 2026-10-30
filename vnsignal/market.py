"""Quy tắc phiên giao dịch thị trường VN."""

from datetime import datetime, time, timedelta

import pandas as pd


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

from datetime import date, datetime

import pandas as pd

from vnsignal.config import TZ
from vnsignal.data.vci import normalize_ohlcv
from vnsignal.market import drop_unfinished_bars


def test_normalize_ohlcv_converts_unit_and_filters_range():
    # Dạng output thật của vnstock Quote.history (VCI): giá nghìn đồng, có phiên trước start.
    raw = pd.DataFrame({
        "time": pd.to_datetime(["2019-12-31", "2020-01-02", "2020-01-02", "2020-01-03"]),
        "open": [18.43, 18.27, 18.27, 18.30],
        "high": [18.47, 18.30, 18.30, 18.76],
        "low": [18.14, 18.18, 18.18, 18.27],
        "close": [18.18, 18.27, 18.27, 18.63],
        "volume": [766000, 692100, 692100, 1604350],
    })
    df = normalize_ohlcv(raw, date(2020, 1, 1), date(2020, 1, 31))
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert list(df["date"]) == ["2020-01-02", "2020-01-03"]
    assert list(df["close"]) == [18270, 18630]
    assert df["close"].dtype == "int64"


def _bars(dates):
    return pd.DataFrame({"date": dates, "close": range(len(dates))})


def test_drop_unfinished_bar_during_session():
    now = datetime(2026, 10, 30, 10, 0, tzinfo=TZ)
    df = drop_unfinished_bars(_bars(["2026-10-29", "2026-10-30"]), "14:45", 15, now)
    assert list(df["date"]) == ["2026-10-29"]


def test_keep_today_bar_after_close_buffer():
    now = datetime(2026, 10, 30, 15, 0, tzinfo=TZ)
    df = drop_unfinished_bars(_bars(["2026-10-29", "2026-10-30"]), "14:45", 15, now)
    assert list(df["date"]) == ["2026-10-29", "2026-10-30"]


def test_upcom_closes_later():
    now = datetime(2026, 10, 30, 15, 5, tzinfo=TZ)
    df = drop_unfinished_bars(_bars(["2026-10-29", "2026-10-30"]), "15:00", 15, now)
    assert list(df["date"]) == ["2026-10-29"]

from datetime import date, datetime

import pandas as pd

from vnsignal.config import TZ
from vnsignal.data.vci import camel_to_snake, parse_gap_chart
from vnsignal.market import drop_unfinished_bars


def _ts(d):
    return str(int(datetime.fromisoformat(d + "T00:00:00+00:00").timestamp()))


def test_parse_gap_chart_filters_range_and_dedupes():
    # Dạng response thật của gap-chart: mảng cột, giá theo đồng, t = 00:00 UTC, có phiên trước start.
    payload = [{
        "symbol": "FPT",
        "t": [_ts("2019-12-31"), _ts("2020-01-02"), _ts("2020-01-02"), _ts("2020-01-03")],
        "o": [18430, 18270, 18270, 18300], "h": [18470, 18300, 18300, 18760],
        "l": [18140, 18180, 18180, 18270], "c": [18180, 18270, 18270, 18630],
        "v": [766000, 692100, 692100, 1604350],
    }]
    df = parse_gap_chart(payload, date(2020, 1, 1), date(2020, 1, 31))
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert list(df["date"]) == ["2020-01-02", "2020-01-03"]
    assert list(df["close"]) == [18270, 18630]
    assert df["close"].dtype == "int64"
    assert parse_gap_chart([], date(2020, 1, 1), date(2020, 1, 31)).empty


def test_camel_to_snake_matches_stored_field_names():
    assert camel_to_snake("highestPrice1Year") == "highest_price1_year"
    assert camel_to_snake("evToEbitda") == "ev_to_ebitda"
    assert camel_to_snake("upsideToTargetPercent") == "upside_to_target_percent"


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

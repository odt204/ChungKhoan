from datetime import date, datetime

import pandas as pd

from vnsignal import live
from vnsignal.config import TZ, load_config
from vnsignal.sitebuilder import build, live_view

CFG = load_config()


def vn(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def test_in_session_window():
    assert live.in_session(vn(2026, 11, 16, 9, 0), CFG)          # thứ Hai 9:00
    assert live.in_session(vn(2026, 11, 16, 15, 5), CFG)
    assert not live.in_session(vn(2026, 11, 16, 8, 59), CFG)
    assert not live.in_session(vn(2026, 11, 16, 15, 6), CFG)
    assert not live.in_session(vn(2026, 11, 14, 10, 0), CFG)     # thứ Bảy


class FakeSource:
    def __init__(self, rows):
        self.rows = rows

    def get_ohlcv(self, symbol, start, end):
        return pd.DataFrame(self.rows.get(symbol, []), columns=["date", "open", "high", "low", "close", "volume"])


def test_fetch_live_uses_today_bar_and_previous_close():
    src = FakeSource({
        "FPT": [("2026-11-13", 49500, 51000, 49100, 50100, 100), ("2026-11-16", 50000, 50900, 49900, 50600, 200)],
        "ACV": [("2026-11-13", 40000, 40500, 39800, 40000, 100)],          # chưa có nến hôm nay
    })
    out = live.fetch_live(src, ["FPT", "ACV"], vn(2026, 11, 16, 10, 45))
    assert list(out) == ["FPT"]
    f = out["FPT"]
    assert (f["price"], f["prev_close"], f["low"], f["volume"]) == (50600, 50100, 49900, 200)
    assert round(f["change"], 4) == round(50600 / 50100 - 1, 4)
    assert f["at"] == "2026-11-16T10:45+07:00"


def sig(signal="HOLD", sl=49723, tp=57166):
    return {"signal": signal, "stop_loss": sl, "take_profit": tp, "date": "2026-11-13"}


def bar(low, high, price=None):
    return {"low": low, "high": high, "price": price or low, "change": -0.01, "at": "2026-11-16T10:45+07:00"}


def test_level_events():
    assert live.level_events(bar(49700, 50500), sig()) == [("SL", 49723.0)]
    assert live.level_events(bar(56000, 57200), sig()) == [("TP", 57166.0)]
    assert live.level_events(bar(50000, 51000), sig()) == []
    assert live.level_events(bar(40000, 60000), sig("SELL")) == []     # BÁN: đã là tín hiệu thoát


def test_alert_once_per_event_per_day():
    state, ev = live.new_events(None, "2026-11-16", "FPT", [("SL", 49723.0)])
    assert ev == [("SL", 49723.0)]
    live.mark_sent(state, "FPT", "SL")
    state, ev = live.new_events(state, "2026-11-16", "FPT", [("SL", 49723.0), ("TP", 57166.0)])
    assert ev == [("TP", 57166.0)]                                     # SL đã báo hôm nay
    state, ev = live.new_events(state, "2026-11-17", "FPT", [("SL", 49723.0)])
    assert ev == [("SL", 49723.0)] and state["sent"] == {}              # ngày mới → báo lại


def test_event_message():
    msg = live.event_message("FPT", "SL", 49723, {**bar(49600, 50500, 49650), "change": -0.009}, sig())
    assert "FPT chạm mức cắt lỗ" in msg and "10:45" in msg and "49.723" in msg
    assert "GIỮ" in msg and msg.rstrip().endswith("không phải khuyến nghị đầu tư.")


def test_live_view_state():
    s = {"signal": "HOLD", "stop_loss": 49723, "take_profit": 57166}
    assert live_view({**bar(49000, 50000, 49500)}, s)["state"] == "below_sl"
    assert live_view({**bar(57000, 58000, 57500)}, s)["state"] == "above_tp"
    assert live_view({**bar(50000, 51000, 50500)}, s)["state"] is None
    assert live_view(None, s) is None


def test_site_shows_live_block(tmp_path):
    lv = {"FPT": {"date": "2026-11-16", "at": "2026-11-16T10:45+07:00", "price": 50600.0, "open": 50000.0,
                  "high": 50900.0, "low": 49900.0, "volume": 2030600, "prev_close": 50100.0, "change": 0.00998}}
    out = tmp_path / "site"
    build(CFG, out, date(2026, 11, 16), "10:45 16/11/2026", "2026-11-16T10:45:00+07:00", live=lv)
    fpt = (out / "FPT.html").read_text(encoding="utf-8")
    assert "Giá tạm tính lúc 10:45" in fpt and "50.600" in fpt
    assert "Giá tạm tính" not in (out / "ACV.html").read_text(encoding="utf-8")
    assert "Đang trong phiên" in (out / "index.html").read_text(encoding="utf-8")

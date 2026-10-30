import pandas as pd

from vnsignal import explain
from vnsignal.config import load_config

CFG = load_config()


def row(**kw):
    base = dict(close=100.0, ema_fast=90.0, ema_mid=85.0, ema_slow=80.0, rsi=55.0, macd_cross=0, macd_hist=1.0,
                volume=1000, vol_ma=1000, prev_close=99.0, high_n=110.0, low_n=90.0)
    base.update(kw)
    return pd.Series(base)


def test_plain_reasons_directions():
    up = explain.plain_reasons(row(close=120.0, volume=2000), CFG)
    assert [r["dir"] for r in up] == ["up", "up", "up", "up"]
    assert up[0]["title"] == "Xu hướng tăng" and up[3]["title"] == "Vượt đỉnh gần đây"

    down = explain.plain_reasons(row(close=70.0, rsi=75.0, macd_hist=-1.0, low_n=80.0, prev_close=72.0, volume=2000), CFG)
    assert down[0]["title"] == "Xu hướng giảm"
    assert down[1]["title"] == "Đã tăng quá nóng"      # RSI > 70
    assert down[2]["title"] == "Bị bán mạnh"
    assert down[3]["title"] == "Thủng đáy gần đây"

    mixed = explain.plain_reasons(row(close=88.0, low_n=85.0), CFG)  # trên TB50/200, dưới TB20; trong vùng 85–110
    assert mixed[0]["dir"] == "flat" and mixed[3]["dir"] == "flat"


def test_macd_cross_takes_priority():
    assert explain.plain_reasons(row(macd_cross=-1, rsi=20.0), CFG)[1]["title"] == "Đà giảm vừa xuất hiện"


def test_action_texts():
    sig = {"signal": "BUY", "stop_loss": 9000, "take_profit": 12000, "position_pct": 0.1}
    buy = explain.action(sig, -0.1, 0.2)
    assert "9.000" in buy["text"] and "T+2" in buy["text"] and "10,0%" in buy["text"]
    assert explain.action({**sig, "signal": "SELL"}, -0.1, 0.2)["title"].startswith("Nghiêng về giảm")
    assert "chờ tín hiệu MUA" in explain.action({**sig, "signal": "HOLD"}, -0.1, 0.2)["text"]


def test_backtest_verdict_handles_negative_returns():
    summary = {"rows": [
        {"key": "cfg_oos", "start": "2024-01-02", "end": "2026-10-29", "cagr": -0.014, "max_drawdown": -0.089},
        {"key": "bh_oos", "start": "2024-01-02", "end": "2026-10-29", "cagr": -0.058, "max_drawdown": -0.521},
    ]}
    p = explain.backtest_plain(summary)
    assert p["win"] and "TỐT HƠN" in p["verdict"] and "-1,4%/năm so với -5,8%/năm" in p["verdict"]
    assert explain.backtest_plain(None) is None


def test_labels():
    assert [explain.confidence_label(c) for c in (10, 45, 70)] == ["Yếu", "Trung bình", "Mạnh"]
    assert [explain.sentiment_label(s) for s in (-0.5, 0.0, 0.5, None)] == ["Tiêu cực", "Trung tính", "Tích cực", "Chưa chấm"]
    assert explain.vn_num(52700) == "52.700" and explain.vn_pct(-0.0571) == "-5,7%"

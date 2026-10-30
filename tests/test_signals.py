import numpy as np
import pandas as pd
import pytest

from vnsignal import indicators
from vnsignal.config import load_config
from vnsignal.signals.engine import SIGNAL_COLUMNS, classify, composite, generate, position_pct, position_shares

CFG = load_config()


def trend_bars(n=300, drift=0.004, seed=1):
    rng = np.random.default_rng(seed)
    close = 10_000 * np.cumprod(1 + drift + rng.normal(0, 0.01, n))
    return pd.DataFrame({
        "date": pd.bdate_range("2022-01-03", periods=n).strftime("%Y-%m-%d"),
        "open": close * 0.998, "high": close * 1.01, "low": close * 0.99, "close": close.round(),
        "volume": rng.integers(500_000, 1_500_000, n),
    })


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 50, dtype=float))
    assert indicators.rsi(up).iloc[-1] == 100
    r = indicators.rsi(trend_bars()["close"])
    assert r.dropna().between(0, 100).all()


def test_atr_constant_range():
    df = pd.DataFrame({"high": [110.0] * 30, "low": [100.0] * 30, "close": [105.0] * 30})
    assert indicators.atr(df, 14).iloc[-1] == pytest.approx(10)


def test_recent_cross_window():
    a = pd.Series([0, 0, 2, 2, 2, 2, 0], dtype=float)
    b = pd.Series([1] * 7, dtype=float)
    assert list(indicators.recent_cross(a, b, 3)) == [0, 0, 1, 1, 1, 0, -1]


def test_composite_and_classify():
    scores = pd.DataFrame({"trend": [1.0, -1.0, 0.0], "momentum": [1.0, -0.5, 0.2]})
    s = composite(scores, {"trend": 1, "momentum": 1})
    assert list(s) == [1.0, -0.75, 0.1]
    assert list(classify(s, 0.4, 0.4)) == ["BUY", "SELL", "HOLD"]


def test_position_pct_risk_and_cap():
    assert position_pct(10_000, 8_000, CFG) == pytest.approx(0.10)   # 2% × 10000 / 2000
    assert position_pct(10_000, 9_900, CFG) == pytest.approx(0.35)   # bị chặn 35%
    assert position_pct(10_000, 10_000, CFG) == 0.0


def test_position_shares_rounds_down_to_lot():
    assert position_shares(100_000_000, 0.10, 52_700, 100) == 100  # 189.7 cp → 100
    assert position_shares(100_000_000, 0.35, 21_100, 100) == 1_600  # 1658.7 cp → 1600


def test_generate_output_shape_and_uptrend():
    sig = generate(trend_bars(), CFG, "FPT")
    assert list(sig.columns) == SIGNAL_COLUMNS
    assert len(sig) == 300 - 199  # bỏ warm-up EMA200
    assert sig["signal"].isin(["BUY", "SELL", "HOLD"]).all()
    assert sig["confidence"].between(0, 100).all()
    assert (sig["stop_loss"] < sig["close"]).all() and (sig["take_profit"] > sig["close"]).all()
    assert (sig.loc[sig["signal"] != "BUY", "position_pct"] == 0).all()
    assert (sig["reasons"].str.count(r" \| ") == 2).all()  # đúng 3 lý do
    assert (sig["signal"] == "BUY").sum() > (sig["signal"] == "SELL").sum()


def test_generate_is_causal():
    # Tín hiệu của một phiên không đổi khi thêm dữ liệu tương lai
    bars = trend_bars()
    full = generate(bars, CFG, "FPT").set_index("date")
    part = generate(bars.iloc[:250], CFG, "FPT").set_index("date")
    pd.testing.assert_frame_equal(full.loc[part.index], part)

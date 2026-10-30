import numpy as np
import pandas as pd
import pytest

from vnsignal.backtest.engine import buy_and_hold, metrics, simulate
from vnsignal.config import load_config
from vnsignal.market import buy_cost, lock_state, price_band, round_lot, sell_proceeds

CFG = load_config()
CAPITAL = 100_000_000
HOSE = 0.07


def make_bars(n=8, overrides=None):
    """n phiên giá 10.000 đi ngang; overrides: {i: (open, high, low, close[, volume])}."""
    overrides = overrides or {}
    rows = []
    for i, d in enumerate(pd.bdate_range("2024-01-01", periods=n)):
        o, h, lo, c, v = 10_000, 10_100, 9_900, 10_000, 1_000_000
        if i in overrides:
            vals = overrides[i]
            o, h, lo, c = vals[:4]
            v = vals[4] if len(vals) > 4 else v
        rows.append((d.strftime("%Y-%m-%d"), o, h, lo, c, v))
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def run(bars, signals: dict, limit=HOSE):
    sig = np.array(["HOLD"] * len(bars), dtype=object)
    for i, s in signals.items():
        sig[i] = s
    atr = np.full(len(bars), 1_000.0)  # SL = entry - 2000, TP = entry + 3000
    return simulate(bars, sig, atr, bars["date"][1], None, CFG, limit, CAPITAL)


# --- market helpers -------------------------------------------------------

def test_fees_and_tax():
    t = CFG["trading"]
    assert buy_cost(100, 10_000, t) == pytest.approx(1_000_000 * 1.0015)
    assert sell_proceeds(100, 10_000, t) == pytest.approx(1_000_000 * (1 - 0.0015 - 0.001))


def test_round_lot():
    assert round_lot(1_299, 100) == 1_200
    assert round_lot(99, 100) == 0


def test_price_band_and_locks():
    assert price_band(10_000, 0.07) == pytest.approx((9_300, 10_700))
    assert lock_state(10_700, 10_700, 10_700, 10_000, 0.07) == "up"
    assert lock_state(9_300, 9_300, 9_300, 10_000, 0.07) == "down"
    assert lock_state(10_700, 10_600, 10_700, 10_000, 0.07) is None  # có giao dịch dưới trần
    assert lock_state(10_700, 10_700, 10_700, 10_000, 0.15) is None  # UPCOM ±15%: +7% không phải trần


# --- backtest -------------------------------------------------------------

def test_t_plus_2_sell_only_from_afternoon_t2():
    # BUY ở phiên 1 → mua phiên 2 (T). SELL ngay phiên 2 → phiên 3 (T+1) chưa bán được,
    # phiên 4 (T+2) bán tại giá đóng cửa (ATC).
    bars = make_bars(overrides={4: (10_000, 10_100, 9_900, 10_050)})
    res = run(bars, {1: "BUY", 2: "SELL"})
    assert len(res.trades) == 1
    tr = res.trades[0]
    assert tr.entry_date == bars["date"][2]
    assert tr.exit_date == bars["date"][4]
    assert tr.exit_price == 10_050
    assert tr.exit_reason == "SELL"


def test_no_stop_loss_before_t2():
    # Phiên T+1 thủng SL nhưng chưa được bán → vị thế vẫn giữ, bán ở T+2 theo ATC.
    bars = make_bars(overrides={3: (9_500, 9_600, 7_500, 9_400), 4: (9_400, 9_500, 9_300, 9_350)})
    res = run(bars, {1: "BUY"})
    tr = res.trades[0]
    assert tr.exit_date == bars["date"][4]
    assert tr.exit_reason == "SL"
    assert tr.exit_price == 9_350


def test_fees_lot_and_position_size():
    bars = make_bars(overrides={4: (10_000, 10_100, 9_900, 10_050)})
    tr = run(bars, {1: "BUY", 2: "SELL"}).trades[0]
    # rủi ro 2% vốn / (2×ATR=2000) × giá 10000 = 10% vốn → 1000 cp, bội số lô 100
    assert tr.shares == 1_000 and tr.shares % 100 == 0
    assert tr.cost == pytest.approx(1_000 * 10_000 * 1.0015)
    assert tr.proceeds == pytest.approx(1_000 * 10_050 * (1 - 0.0025))


def test_position_capped_at_35_percent():
    atr = np.full(8, 1.0)  # stop rất sát → size theo rủi ro rất lớn → bị chặn 35%
    sig = np.array(["HOLD", "BUY"] + ["HOLD"] * 6, dtype=object)
    bars = make_bars()
    tr = simulate(bars, sig, atr, bars["date"][1], None, CFG, HOSE, CAPITAL).trades[0]
    assert tr.shares == 3_500


def test_buy_blocked_when_locked_at_ceiling():
    bars = make_bars(overrides={2: (10_700, 10_700, 10_700, 10_700)})
    assert run(bars, {1: "BUY"}).trades == []


def test_buy_blocked_when_no_volume():
    bars = make_bars(overrides={2: (10_000, 10_000, 10_000, 10_000, 0)})
    assert run(bars, {1: "BUY"}).trades == []


def test_sell_deferred_when_locked_at_floor():
    bars = make_bars(overrides={4: (9_300, 9_300, 9_300, 9_300), 5: (9_400, 9_500, 9_300, 9_450)})
    tr = run(bars, {1: "BUY", 2: "SELL"}).trades[0]
    assert tr.exit_date == bars["date"][5]
    assert tr.exit_price == 9_400  # khớp giá mở cửa phiên kế tiếp


def test_stop_loss_and_gap_from_t3():
    # Phiên 5 (T+3): chạm SL 8000 trong phiên → khớp tại SL (sàn = 8500 × 0.93 = 7905)
    bars = make_bars(overrides={4: (9_500, 9_600, 8_500, 8_500), 5: (8_600, 8_700, 7_950, 8_200)})
    tr = run(bars, {1: "BUY"}).trades[0]
    assert (tr.exit_reason, tr.exit_price, tr.exit_date) == ("SL", 8_000, bars["date"][5])
    # Gap xuống dưới SL → khớp giá mở cửa
    bars = make_bars(overrides={4: (9_500, 9_600, 9_000, 8_600), 5: (8_000, 8_100, 7_900, 8_000)})
    tr = run(bars, {1: "BUY"}).trades[0]
    assert (tr.exit_reason, tr.exit_price) == ("SL", 8_000)
    bars = make_bars(overrides={4: (9_500, 9_600, 9_000, 8_400), 5: (7_900, 8_000, 7_820, 7_900)})
    tr = run(bars, {1: "BUY"}).trades[0]
    assert (tr.exit_reason, tr.exit_price) == ("SL", 7_900)


def test_fill_price_clamped_to_band():
    # Dữ liệu lỗi: open vượt trần → khớp tối đa giá trần
    bars = make_bars(overrides={2: (11_000, 11_000, 10_500, 10_600)})
    tr = run(bars, {1: "BUY", 2: "SELL"}).trades[0]
    assert tr.entry_price == pytest.approx(10_700)


def test_open_position_closed_at_end_and_metrics():
    bars = make_bars(overrides={7: (10_000, 10_100, 9_900, 10_200)})
    res = run(bars, {1: "BUY"})
    assert res.trades[-1].exit_reason == "Cuối kỳ"
    m = metrics(res, CAPITAL)
    assert m["trades"] == 1 and m["win_rate"] == 1.0
    assert m["total_return"] == pytest.approx(res.equity.iloc[-1] / CAPITAL - 1)


def test_buy_and_hold_all_in_with_costs():
    bars = make_bars(overrides={7: (10_000, 10_100, 9_900, 11_000)})
    res = buy_and_hold(bars, bars["date"][1], None, CFG, HOSE, CAPITAL)
    tr = res.trades[0]
    assert tr.shares == round_lot(CAPITAL / (10_000 * 1.0015), 100)
    expected = CAPITAL - tr.cost + tr.shares * 11_000 * (1 - 0.0025)
    assert res.equity.iloc[-1] == pytest.approx(expected)

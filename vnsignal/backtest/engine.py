"""Backtest event-driven, long-only, một mã.

Quy ước khớp lệnh:
- Tín hiệu tính ở giá đóng cửa phiên t → lệnh đặt cho phiên t+1, khớp giá mở cửa.
- Mua: bị huỷ nếu phiên t+1 khóa trần hoặc volume = 0.
- Mua ngày T chỉ bán được từ phiên chiều T+settlement_days (đếm theo phiên giao dịch):
  * đúng phiên T+2: mọi lệnh thoát (tín hiệu SELL, chạm SL/TP) khớp giá đóng cửa (ATC);
  * từ T+3: SELL khớp giá mở cửa; SL/TP khớp tại mức SL/TP (hoặc giá mở cửa nếu gap qua).
  * Cùng phiên chạm cả SL và TP → giả định chạm SL trước (bảo thủ).
  * Thủng SL trước khi được bán (T, T+1) → bán ngay phiên được phép đầu tiên.
- Bán bị hoãn nếu phiên khóa sàn hoặc volume = 0 (lệnh SELL giữ nguyên tới phiên sau).
- Giá khớp luôn bị kẹp trong biên độ [sàn, trần] so với close phiên trước.
- Số lượng làm tròn xuống theo lô; phí mua, phí bán + thuế bán trừ vào tiền.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from vnsignal.market import buy_cost, lock_state, price_band, round_lot, sell_proceeds
from vnsignal.signals.engine import position_pct


@dataclass
class Trade:
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: int
    cost: float
    proceeds: float
    exit_reason: str

    @property
    def pnl(self) -> float:
        return self.proceeds - self.cost

    @property
    def ret(self) -> float:
        return self.pnl / self.cost


@dataclass
class Result:
    trades: list[Trade] = field(default_factory=list)
    equity: pd.Series | None = None
    in_market: pd.Series | None = None


def simulate(
    bars: pd.DataFrame,
    signal: np.ndarray,
    atr: np.ndarray,
    start: str,
    end: str | None,
    cfg: dict,
    limit: float,
    capital: float,
) -> Result:
    """`bars` có cột date/open/high/low/close/volume, `signal`/`atr` cùng độ dài với `bars`.
    Chỉ giao dịch trong [start, end]; dữ liệu trước start chỉ dùng làm giá tham chiếu."""
    trading, risk = cfg["trading"], cfg["risk"]
    lot, settle = trading["lot_size"], trading["settlement_days"]
    dates = bars["date"].to_numpy()
    o, h, lo, c, v = (bars[k].to_numpy(dtype=float) for k in ["open", "high", "low", "close", "volume"])
    mask = (dates >= start) & ((dates <= end) if end else True)
    idx = np.flatnonzero(mask)
    if len(idx) == 0 or idx[0] == 0:
        raise ValueError("Cửa sổ backtest cần ít nhất 1 phiên trước start làm giá tham chiếu")

    cash, shares = float(capital), 0
    entry_i = entry_px = sl = tp = cost = None
    pending_buy = pending_sell = stop_hit = False
    pending_atr = 0.0
    trades, equity, in_mkt = [], [], []

    for i in idx:
        ref = c[i - 1]
        floor_px, ceil_px = price_band(ref, limit)
        lock = lock_state(h[i], lo[i], c[i], ref, limit)
        tradable = v[i] > 0
        exited_today = False

        # 1) Thoát vị thế
        if shares and i - entry_i < settle and lo[i] <= sl:
            stop_hit = True  # thủng SL khi chưa được bán → bán ngay khi đủ T+2
        if shares and i - entry_i >= settle and tradable and lock != "down":
            held = i - entry_i
            px = reason = None
            if held == settle:  # chỉ phiên chiều → khớp ATC
                if pending_sell:
                    px, reason = c[i], "SELL"
                elif stop_hit or lo[i] <= sl:
                    px, reason = c[i], "SL"
                elif h[i] >= tp:
                    px, reason = c[i], "TP"
            else:
                if pending_sell:
                    px, reason = o[i], "SELL"
                elif stop_hit or o[i] <= sl:
                    px, reason = o[i], "SL"
                elif lo[i] <= sl:
                    px, reason = sl, "SL"
                elif o[i] >= tp:
                    px, reason = o[i], "TP"
                elif h[i] >= tp:
                    px, reason = tp, "TP"
            if px is not None:
                px = min(max(px, floor_px), ceil_px)
                proceeds = sell_proceeds(shares, px, trading)
                cash += proceeds
                trades.append(Trade(dates[entry_i], dates[i], entry_px, px, shares, cost, proceeds, reason))
                shares, pending_sell, stop_hit, exited_today = 0, False, False, True

        # 2) Vào vị thế
        if pending_buy and not shares and not exited_today and tradable and lock != "up":
            px = min(max(o[i], floor_px), ceil_px)
            stop = px - risk["stop_atr"] * pending_atr
            eq_prev = cash  # đang không giữ cổ phiếu → equity = cash
            n = round_lot(eq_prev * position_pct(px, stop, cfg) / px, lot)
            while n > 0 and buy_cost(n, px, trading) > cash:
                n -= lot
            if n > 0:
                cost = buy_cost(n, px, trading)
                cash -= cost
                shares, entry_i, entry_px = n, i, px
                sl, tp = stop, px + risk["take_profit_atr"] * pending_atr
        pending_buy = False

        # 3) Cuối phiên: tín hiệu mới → lệnh cho phiên sau
        if shares:
            pending_sell = pending_sell or signal[i] == "SELL"
        elif signal[i] == "BUY":
            pending_buy, pending_atr = True, atr[i]

        equity.append(cash + shares * c[i])
        in_mkt.append(shares > 0)

    if shares:  # đóng vị thế cuối kỳ theo giá đóng cửa
        last = idx[-1]
        proceeds = sell_proceeds(shares, c[last], trading)
        trades.append(Trade(dates[entry_i], dates[last], entry_px, c[last], shares, cost, proceeds, "Cuối kỳ"))
        equity[-1] = cash + proceeds

    index = pd.Index(dates[idx], name="date")
    return Result(trades, pd.Series(equity, index=index), pd.Series(in_mkt, index=index))


def buy_and_hold(bars: pd.DataFrame, start: str, end: str | None, cfg: dict, limit: float, capital: float) -> Result:
    """Mua toàn bộ vốn (theo lô, có phí) ở giá mở cửa phiên đầu tiên khớp được trong kỳ,
    giữ đến hết kỳ, bán theo giá đóng cửa phiên cuối (có phí + thuế)."""
    trading, lot = cfg["trading"], cfg["trading"]["lot_size"]
    dates = bars["date"].to_numpy()
    o, h, lo, c, v = (bars[k].to_numpy(dtype=float) for k in ["open", "high", "low", "close", "volume"])
    idx = np.flatnonzero((dates >= start) & ((dates <= end) if end else True))
    cash, shares, entry_i, cost = float(capital), 0, None, 0.0
    equity, in_mkt = [], []
    for i in idx:
        if not shares and v[i] > 0 and lock_state(h[i], lo[i], c[i], c[i - 1], limit) != "up":
            n = round_lot(cash / (o[i] * (1 + trading["buy_fee"])), lot)
            if n > 0:
                shares, entry_i, cost = n, i, buy_cost(n, o[i], trading)
                cash -= cost
        equity.append(cash + shares * c[i])
        in_mkt.append(shares > 0)
    trades = []
    if shares:
        last = idx[-1]
        proceeds = sell_proceeds(shares, c[last], trading)
        trades.append(Trade(dates[entry_i], dates[last], o[entry_i], c[last], shares, cost, proceeds, "Cuối kỳ"))
        equity[-1] = cash + proceeds
    index = pd.Index(dates[idx], name="date")
    return Result(trades, pd.Series(equity, index=index), pd.Series(in_mkt, index=index))


def metrics(res: Result, capital: float) -> dict:
    eq = res.equity
    rets = [t.ret for t in res.trades]
    gains = sum(t.pnl for t in res.trades if t.pnl > 0)
    losses = -sum(t.pnl for t in res.trades if t.pnl < 0)
    days = (pd.Timestamp(eq.index[-1]) - pd.Timestamp(eq.index[0])).days or 1
    total = eq.iloc[-1] / capital - 1
    return {
        "start": eq.index[0],
        "end": eq.index[-1],
        "trades": len(res.trades),
        "win_rate": (sum(r > 0 for r in rets) / len(rets)) if rets else float("nan"),
        "profit_factor": (gains / losses) if losses > 0 else (float("inf") if gains > 0 else float("nan")),
        "total_return": total,
        "cagr": (1 + total) ** (365.25 / days) - 1 if total > -1 else -1.0,
        "max_drawdown": float((eq / eq.cummax() - 1).min()),
        "exposure": float(res.in_market.mean()),
    }

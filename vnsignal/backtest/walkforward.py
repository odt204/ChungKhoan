"""Walk-forward: tối ưu trọng số + ngưỡng trên in-sample, kiểm tra out-of-sample."""

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from vnsignal import indicators
from vnsignal.backtest.engine import Result, buy_and_hold, metrics, simulate
from vnsignal.signals.engine import classify, composite, rule_scores, weights_for


@dataclass
class Run:
    label: str
    weights: dict
    thresholds: tuple[float, float]  # (mua, bán)
    result: Result
    metrics: dict


@dataclass
class SymbolBacktest:
    symbol: str
    is_opt: Run | None   # None nếu không bộ trọng số nào đủ min_trades trong in-sample
    oos_opt: Run | None
    full_cfg: Run
    oos_cfg: Run
    bh_is: Run
    bh_oos: Run
    bh_full: Run
    combos_tested: int


def prepare(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    ind = indicators.compute(df, cfg)
    scores = rule_scores(ind, cfg)
    warm = ind[["ema_slow", "rsi", "macd_signal", "atr", "vol_ma", "high_n", "low_n"]].isna().any(axis=1)
    scores[warm] = np.nan  # warm-up: score NaN → HOLD
    return df.reset_index(drop=True), scores.reset_index(drop=True), ind["atr"].to_numpy()


def weight_combos(names: list[str], grid: list[float]) -> list[dict]:
    seen, out = set(), []
    for combo in product(grid, repeat=len(names)):
        total = sum(combo)
        if total <= 0:
            continue
        key = tuple(round(x / total, 6) for x in combo)
        if key not in seen:
            seen.add(key)
            out.append(dict(zip(names, combo)))
    return out


def run(bars, scores, atr, weights, thresholds, start, end, cfg, limit, capital, label) -> Run:
    sig = classify(composite(scores, weights), *thresholds).to_numpy()
    res = simulate(bars, sig, atr, start, end, cfg, limit, capital)
    return Run(label, weights, thresholds, res, metrics(res, capital))


def bh(bars, start, end, cfg, limit, capital, label) -> Run:
    res = buy_and_hold(bars, start, end, cfg, limit, capital)
    return Run(label, {}, (float("nan"), float("nan")), res, metrics(res, capital))


def objective(m: dict) -> float:
    """CAGR chia max drawdown (sàn 5%) — ưu tiên lợi nhuận trên rủi ro, không chỉ lợi nhuận."""
    return m["cagr"] / max(-m["max_drawdown"], 0.05)


def backtest_symbol(symbol: str, df: pd.DataFrame, cfg: dict, capital: float) -> SymbolBacktest:
    bt = cfg["backtest"]
    limit = cfg["exchanges"][cfg["symbols"][symbol]["exchange"]]["price_limit"]
    is_start, is_end = bt["in_sample"]
    oos_start = bt["out_of_sample_start"]
    full_start = cfg["start_date"]
    bars, scores, atr = prepare(df, cfg)
    # Bắt đầu giao dịch khi đã qua warm-up chỉ báo
    first_valid = bars.loc[scores.notna().all(axis=1).idxmax(), "date"]
    is_start = max(is_start, first_valid)
    full_start = max(full_start, first_valid)

    combos = weight_combos(list(scores.columns), bt["weight_grid"])
    best = None
    for w in combos:
        score = composite(scores, w)
        for th in bt["threshold_grid"]:
            sig = classify(score, th, th).to_numpy()
            res = simulate(bars, sig, atr, is_start, is_end, cfg, limit, capital)
            m = metrics(res, capital)
            if m["trades"] < bt["min_trades"]:
                continue
            if best is None or objective(m) > objective(best.metrics):
                best = Run("In-sample (tối ưu)", w, (th, th), res, m)

    args = (cfg, limit, capital)
    oos_opt = None
    if best is not None:
        oos_opt = run(bars, scores, atr, best.weights, best.thresholds, oos_start, None, *args, "Out-of-sample")
    w_cfg = weights_for(cfg, symbol)
    th_cfg = (cfg["signals"]["buy_threshold"], cfg["signals"]["sell_threshold"])
    return SymbolBacktest(
        symbol=symbol,
        is_opt=best,
        oos_opt=oos_opt,
        full_cfg=run(bars, scores, atr, w_cfg, th_cfg, full_start, None, *args, "Toàn kỳ"),
        oos_cfg=run(bars, scores, atr, w_cfg, th_cfg, oos_start, None, *args, "Out-of-sample"),
        bh_is=bh(bars, is_start, is_end, *args, "Buy-and-hold in-sample"),
        bh_oos=bh(bars, oos_start, None, *args, "Buy-and-hold out-of-sample"),
        bh_full=bh(bars, full_start, None, *args, "Buy-and-hold toàn kỳ"),
        combos_tested=len(combos) * len(bt["threshold_grid"]),
    )

"""Composite signal engine: điểm tổng hợp có trọng số từ các rule → BUY/SELL/HOLD,
kèm entry / stop-loss / take-profit / tỷ trọng vốn và 3 lý do tiếng Việt."""

import math

import numpy as np
import pandas as pd

from vnsignal import indicators
from vnsignal.signals.rules import RULES

SIGNAL_COLUMNS = [
    "date", "close", "score", "signal", "confidence", "stop_loss", "take_profit", "position_pct", "reasons",
]


def weights_for(cfg: dict, symbol: str) -> dict:
    return cfg["symbols"][symbol].get("weights", cfg["signals"]["weights"])


def rule_scores(ind: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    return pd.DataFrame({r.name: r(cfg).score(ind) for r in RULES}, index=ind.index)


def composite(scores: pd.DataFrame, weights: dict) -> pd.Series:
    w = pd.Series({k: weights.get(k, 0.0) for k in scores.columns}, dtype=float)
    if w.sum() <= 0:
        raise ValueError("Tổng trọng số phải > 0")
    return (scores * w).sum(axis=1) / w.sum()


def classify(score: pd.Series, buy_threshold: float, sell_threshold: float) -> pd.Series:
    return pd.Series(
        np.select([score >= buy_threshold, score <= -sell_threshold], ["BUY", "SELL"], "HOLD"), index=score.index
    )


def position_pct(entry: float, stop: float, cfg: dict) -> float:
    """Tỷ trọng vốn cho 1 lệnh mua: rủi ro (entry - stop) không quá risk_per_trade_pct vốn,
    giá trị vị thế không quá max_position_pct vốn. Không phụ thuộc số vốn tuyệt đối."""
    r = cfg["risk"]
    per_share_risk = entry - stop
    if per_share_risk <= 0:
        return 0.0
    return min(r["max_position_pct"], r["risk_per_trade_pct"] * entry / per_share_risk)


def position_shares(capital: float, pct: float, entry: float, lot: int) -> int:
    """Số cổ phiếu (làm tròn xuống theo lô) cho tỷ trọng `pct` của `capital`."""
    if entry <= 0 or pct <= 0:
        return 0
    return int(math.floor(capital * pct / entry / lot)) * lot


def generate(df: pd.DataFrame, cfg: dict, symbol: str) -> pd.DataFrame:
    """Tín hiệu cho mọi phiên đủ dữ liệu chỉ báo (bỏ giai đoạn warm-up)."""
    s, r = cfg["signals"], cfg["risk"]
    weights = weights_for(cfg, symbol)
    ind = indicators.compute(df, cfg)
    ind = ind.dropna(subset=["ema_slow", "rsi", "macd_signal", "atr", "vol_ma", "high_n", "low_n"])
    scores = rule_scores(ind, cfg)
    score = composite(scores, weights)
    signal = classify(score, s["buy_threshold"], s["sell_threshold"])

    out = pd.DataFrame({"date": ind["date"], "close": ind["close"], "score": score.round(3), "signal": signal})
    out["confidence"] = (score.abs() * 100).round().clip(0, 100).astype(int)
    out["stop_loss"] = (ind["close"] - r["stop_atr"] * ind["atr"]).round().astype("int64")
    out["take_profit"] = (ind["close"] + r["take_profit_atr"] * ind["atr"]).round().astype("int64")
    out["position_pct"] = [
        round(position_pct(c, sl, cfg), 4) if sig == "BUY" else 0.0
        for c, sl, sig in zip(out["close"], out["stop_loss"], out["signal"])
    ]

    rules = {rc.name: rc(cfg) for rc in RULES}
    contrib = scores.mul(pd.Series(weights)).abs()
    reasons = []
    for idx in ind.index:
        top = contrib.loc[idx].sort_values(ascending=False, kind="stable").index[:3]
        reasons.append(" | ".join(rules[name].reason(ind.loc[idx]) for name in top))
    out["reasons"] = reasons
    return out[SIGNAL_COLUMNS].reset_index(drop=True)

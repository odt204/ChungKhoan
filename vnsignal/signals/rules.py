"""Các rule chấm điểm. Mỗi rule trả về điểm trong [-1, 1] cho từng phiên
(dương = ủng hộ MUA, âm = ủng hộ BÁN) và câu giải thích tiếng Việt."""

import numpy as np
import pandas as pd


def _fmt(v: float) -> str:
    return f"{v:,.0f}"


class Rule:
    name: str

    def __init__(self, cfg: dict):
        self.cfg = cfg["signals"]

    def score(self, ind: pd.DataFrame) -> pd.Series:
        raise NotImplementedError

    def reason(self, row: pd.Series) -> str:
        raise NotImplementedError


class TrendRule(Rule):
    """Giá so với EMA nhanh/trung/chậm và vị trí EMA nhanh so với EMA trung."""

    name = "trend"

    def score(self, ind):
        parts = [
            np.sign(ind["close"] - ind["ema_fast"]),
            np.sign(ind["close"] - ind["ema_mid"]),
            np.sign(ind["close"] - ind["ema_slow"]),
            np.sign(ind["ema_fast"] - ind["ema_mid"]),
        ]
        return sum(parts) / len(parts)

    def reason(self, row):
        f, m, s = self.cfg["ema"]
        above = [f"EMA{n}" for n, col in [(f, "ema_fast"), (m, "ema_mid"), (s, "ema_slow")] if row["close"] > row[col]]
        below = [f"EMA{n}" for n, col in [(f, "ema_fast"), (m, "ema_mid"), (s, "ema_slow")] if row["close"] <= row[col]]
        text = "Giá " + "; ".join(
            p for p in [f"trên {', '.join(above)}" if above else "", f"dưới {', '.join(below)}" if below else ""] if p
        )
        if row["ema_cross"] == 1:
            text += f"; EMA{f} vừa cắt lên EMA{m}"
        elif row["ema_cross"] == -1:
            text += f"; EMA{f} vừa cắt xuống EMA{m}"
        return text


class MomentumRule(Rule):
    """RSI quá bán/quá mua + MACD cắt đường tín hiệu."""

    name = "momentum"

    def score(self, ind):
        r = self.cfg["rsi"]
        rsi_s = np.select([ind["rsi"] < r["oversold"], ind["rsi"] > r["overbought"]], [1.0, -1.0], 0.0)
        macd_s = np.where(ind["macd_cross"] != 0, ind["macd_cross"], 0.5 * np.sign(ind["macd_hist"]))
        return pd.Series((rsi_s + macd_s) / 2, index=ind.index)

    def reason(self, row):
        r = self.cfg["rsi"]
        rsi_note = " (quá bán)" if row["rsi"] < r["oversold"] else " (quá mua)" if row["rsi"] > r["overbought"] else ""
        if row["macd_cross"] == 1:
            macd_note = "MACD vừa cắt lên đường tín hiệu"
        elif row["macd_cross"] == -1:
            macd_note = "MACD vừa cắt xuống đường tín hiệu"
        else:
            macd_note = f"MACD {'trên' if row['macd_hist'] > 0 else 'dưới'} đường tín hiệu"
        return f"RSI14 = {row['rsi']:.1f}{rsi_note}; {macd_note}"


class VolumeRule(Rule):
    """Khối lượng đột biến (≥ spike × MA) xác nhận hướng của phiên."""

    name = "volume"

    def score(self, ind):
        spike = ind["volume"] >= self.cfg["volume"]["spike"] * ind["vol_ma"]
        return pd.Series(np.where(spike, np.sign(ind["close"] - ind["prev_close"]), 0.0), index=ind.index)

    def reason(self, row):
        ratio = row["volume"] / row["vol_ma"] if row["vol_ma"] else 0
        n = self.cfg["volume"]["ma"]
        if ratio >= self.cfg["volume"]["spike"]:
            move = "tăng" if row["close"] > row["prev_close"] else "giảm" if row["close"] < row["prev_close"] else "đứng giá"
            return f"Khối lượng đột biến {ratio:.1f}× TB{n}, phiên {move}"
        return f"Khối lượng {ratio:.1f}× TB{n}, chưa xác nhận"


class SupportResistanceRule(Rule):
    """Breakout đỉnh N phiên (+1) / thủng đáy N phiên (-1)."""

    name = "support_resistance"

    def score(self, ind):
        return pd.Series(
            np.select([ind["close"] > ind["high_n"], ind["close"] < ind["low_n"]], [1.0, -1.0], 0.0), index=ind.index
        )

    def reason(self, row):
        n = self.cfg["breakout_window"]
        if row["close"] > row["high_n"]:
            return f"Vượt đỉnh {n} phiên ({_fmt(row['high_n'])})"
        if row["close"] < row["low_n"]:
            return f"Thủng đáy {n} phiên ({_fmt(row['low_n'])})"
        return f"Giá trong vùng {n} phiên {_fmt(row['low_n'])}–{_fmt(row['high_n'])}"


RULES = [TrendRule, MomentumRule, VolumeRule, SupportResistanceRule]

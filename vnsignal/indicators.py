"""Chỉ báo kỹ thuật (chỉ dùng dữ liệu tới phiên hiện tại — không nhìn trước)."""

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI Wilder."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0).where(gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """ATR Wilder."""
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def recent_cross(a: pd.Series, b: pd.Series, lookback: int) -> pd.Series:
    """+1 nếu a vừa cắt lên b trong `lookback` phiên gần nhất, -1 nếu cắt xuống, 0 nếu không.
    Nếu có cả hai, lấy lần cắt gần nhất."""
    above = a > b
    up = above & ~above.shift(1, fill_value=False)
    down = ~above & above.shift(1, fill_value=False)
    event = pd.Series(np.select([up, down], [1, -1], 0), index=a.index, dtype=float)
    last = event.replace(0, np.nan).ffill(limit=lookback - 1)
    return last.fillna(0).astype(int)


def compute(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Thêm toàn bộ cột chỉ báo cần cho rule engine vào bản sao của OHLCV."""
    s = cfg["signals"]
    out = df.copy()
    e_fast, e_mid, e_slow = s["ema"]
    out["ema_fast"] = ema(out["close"], e_fast)
    out["ema_mid"] = ema(out["close"], e_mid)
    out["ema_slow"] = ema(out["close"], e_slow)
    out["ema_cross"] = recent_cross(out["ema_fast"], out["ema_mid"], s["cross_lookback"])
    out["rsi"] = rsi(out["close"], s["rsi"]["period"])
    out = out.join(macd(out["close"], s["macd"]["fast"], s["macd"]["slow"], s["macd"]["signal"]))
    out["macd_cross"] = recent_cross(out["macd"], out["macd_signal"], s["cross_lookback"])
    out["atr"] = atr(out, cfg["risk"]["atr_period"])
    out["vol_ma"] = out["volume"].rolling(s["volume"]["ma"]).mean()
    w = s["breakout_window"]
    out["high_n"] = out["high"].rolling(w).max().shift(1)
    out["low_n"] = out["low"].rolling(w).min().shift(1)
    out["prev_close"] = out["close"].shift(1)
    return out

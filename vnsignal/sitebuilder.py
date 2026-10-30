"""Sinh dashboard tĩnh `site/` từ data đã commit. Chỉ hiển thị tín hiệu, giá, %, chỉ số —
không hiển thị vốn, số cổ phiếu hay số tiền tuyệt đối."""

import json
import math
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from vnsignal import indicators
from vnsignal.alert import DISCLAIMER, LABEL, latest_signal
from vnsignal.config import FUNDAMENTALS_DIR, NEWS_DIR, OHLCV_DIR, REPORTS_DIR, ROOT, SIGNALS_DIR
from vnsignal.store import read_csv, read_json, read_jsonl

SITE_DIR = ROOT / "site"
PKG_DIR = Path(__file__).parent
CHART_LIB = "https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"
NEWS_ON_PAGE = 20
CHANGES_ON_PAGE = 12


def _num(x, digits: int):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), digits) if digits else int(round(float(x)))


def chart_data(symbol: str, ohlcv: pd.DataFrame, signals: pd.DataFrame, cfg: dict) -> dict:
    """Dữ liệu chart dạng cột (gọn): giá, volume, EMA, RSI, MACD, ATR, marker đổi tín hiệu."""
    ind = indicators.compute(ohlcv, cfg)
    col = lambda name, d: [_num(v, d) for v in ind[name]]  # noqa: E731
    f, m, s = cfg["signals"]["ema"]
    return {
        "symbol": symbol,
        "ema_periods": [f, m, s],
        "t": list(ind["date"]),
        "o": col("open", 0), "h": col("high", 0), "l": col("low", 0), "c": col("close", 0),
        "v": col("volume", 0),
        "ema_fast": col("ema_fast", 1), "ema_mid": col("ema_mid", 1), "ema_slow": col("ema_slow", 1),
        "rsi": col("rsi", 1),
        "macd": col("macd", 1), "macd_signal": col("macd_signal", 1), "macd_hist": col("macd_hist", 1),
        "atr": col("atr", 0),
        "rsi_levels": [cfg["signals"]["rsi"]["oversold"], cfg["signals"]["rsi"]["overbought"]],
        "markers": [{"t": c["date"], "s": c["to"]} for c in signal_changes(signals) if c["to"] != "HOLD"],
    }


def signal_changes(signals: pd.DataFrame) -> list[dict]:
    """Các phiên tín hiệu đổi trạng thái (theo thứ tự thời gian)."""
    if signals.empty:
        return []
    prev = signals["signal"].shift(1)
    changed = signals[prev.notna() & (signals["signal"] != prev)]
    return [
        {"date": r.date, "from": p, "to": r.signal, "close": r.close, "confidence": r.confidence}
        for r, p in zip(changed.itertuples(), prev[changed.index])
    ]


def _vn_num(x: float, digits: int = 0) -> str:
    s = f"{x:,.{digits}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _pct(x, digits: int = 1, sign: bool = False) -> str:
    if x == "inf":
        return "∞"
    if x is None:
        return "–"
    prefix = "+" if sign and x > 0 else ""
    return f"{prefix}{_vn_num(x * 100, digits)}%"


def _date_vn(d: str) -> str:
    return datetime.fromisoformat(d[:10]).strftime("%d/%m/%Y") if d else ""


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(PKG_DIR / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["vnd"] = lambda x: _vn_num(float(x))
    env.filters["num"] = lambda x, d=2: _vn_num(float(x), d)
    env.filters["pct"] = _pct
    env.filters["spct"] = lambda x, d=1: _pct(x, d, sign=True)
    env.filters["date_vn"] = _date_vn
    env.filters["pf"] = lambda x: "∞" if x == "inf" else ("–" if x is None else _vn_num(x, 2))
    env.globals.update(LABEL=LABEL, DISCLAIMER=DISCLAIMER, CHART_LIB=CHART_LIB)
    return env


def symbol_view(symbol: str, cfg: dict, today) -> dict:
    ohlcv = read_csv(OHLCV_DIR / f"{symbol}.csv")
    signals = read_csv(SIGNALS_DIR / f"{symbol}.csv")
    sig = latest_signal(symbol, cfg, today)
    prev_close = float(ohlcv["close"].iloc[-2]) if len(ohlcv) > 1 else None
    fundamentals = read_json(FUNDAMENTALS_DIR / f"{symbol}.json") or {}
    news = sorted(read_jsonl(NEWS_DIR / f"{symbol}.jsonl"), key=lambda r: r.get("published_at") or "", reverse=True)
    return {
        "symbol": symbol,
        "exchange": cfg["symbols"][symbol]["exchange"],
        "name": (fundamentals.get("overview") or {}).get("organ_name") or symbol,
        "signal": sig,
        "day_change": (sig["close"] / prev_close - 1) if sig and prev_close else None,
        "sl_pct": (sig["stop_loss"] / sig["close"] - 1) if sig else None,
        "tp_pct": (sig["take_profit"] / sig["close"] - 1) if sig else None,
        "changes": list(reversed(signal_changes(signals)))[:CHANGES_ON_PAGE],
        "news": news[:NEWS_ON_PAGE],
        "backtest": read_json(REPORTS_DIR / f"backtest_{symbol}.json"),
        "chart": chart_data(symbol, ohlcv, signals, cfg),
    }


def build(cfg: dict, out_dir: Path, today, generated_at: str) -> list[Path]:
    """Sinh index.html, {symbol}.html, data/{symbol}.json, assets/*. Trả về danh sách file đã ghi."""
    env = _env()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "data").mkdir(parents=True)
    shutil.copytree(PKG_DIR / "static", out_dir / "assets")
    written = [out_dir / "assets" / p.name for p in (PKG_DIR / "static").iterdir()]

    symbols = list(cfg["symbols"])
    views = [symbol_view(s, cfg, today) for s in symbols]
    common = {"symbols": symbols, "generated_at": generated_at}

    for v in views:
        data_path = out_dir / "data" / f"{v['symbol']}.json"
        data_path.write_text(json.dumps(v["chart"], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        page = out_dir / f"{v['symbol']}.html"
        page.write_text(env.get_template("symbol.html").render(v=v, active=v["symbol"], **common), encoding="utf-8")
        written += [data_path, page]

    index = out_dir / "index.html"
    index.write_text(env.get_template("index.html").render(views=views, active="index", **common), encoding="utf-8")
    written.append(index)
    return written

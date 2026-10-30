"""Cảnh báo Telegram: chỉ gửi khi tín hiệu đổi trạng thái (so với data/alert_state.json),
hoặc gửi bản tổng hợp mọi mã với --summary."""

import logging
import os
from collections.abc import Callable
from datetime import datetime

import requests

from vnsignal.config import NEWS_DIR, SIGNALS_DIR
from vnsignal.sentiment import adjust_confidence, aggregate
from vnsignal.signals.engine import position_shares
from vnsignal.store import read_csv, read_jsonl

log = logging.getLogger("vnsignal")

DISCLAIMER = "Đây là tín hiệu tham khảo, không phải khuyến nghị đầu tư."
LABEL = {"BUY": "MUA", "SELL": "BÁN", "HOLD": "GIỮ"}
ICON = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"

Sender = Callable[[str], bool]


def telegram_sender() -> Sender | None:
    """Sender dùng env TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID; None nếu thiếu env."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.warning("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID → không gửi alert")
        return None

    def send(text: str) -> bool:
        try:
            r = requests.post(
                TELEGRAM_URL.format(token=token),
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                timeout=20,
            )
        except requests.RequestException as e:
            # Thông báo lỗi của requests có thể chứa URL (kèm token) → che token trước khi log
            log.warning("Telegram lỗi kết nối: %s", str(e).replace(token, "***"))
            return False
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code != 200 or not body.get("ok"):
            desc = str(body.get("description", "")).replace(token, "***")
            log.warning("Telegram trả lỗi HTTP %d: %s", r.status_code, desc)
            return False
        return True

    return send


def _fmt(v: float) -> str:
    return f"{v:,.0f}"


def _pct_from(price: float, ref: float) -> str:
    return f"{(price / ref - 1) * 100:+.1f}%"


def latest_signal(symbol: str, cfg: dict, today) -> dict | None:
    """Tín hiệu mới nhất của mã kèm confidence đã điều chỉnh theo sentiment (không có số tiền)."""
    signals = read_csv(SIGNALS_DIR / f"{symbol}.csv")
    if signals.empty:
        return None
    row = signals.iloc[-1]
    ncfg = cfg["news"]
    sentiment, n_news = aggregate(read_jsonl(NEWS_DIR / f"{symbol}.jsonl"), today, ncfg["window_days"])
    confidence = adjust_confidence(row["signal"], int(row["confidence"]), sentiment, ncfg["max_confidence_adjust"])
    return {
        "symbol": symbol,
        "exchange": cfg["symbols"][symbol]["exchange"],
        "date": row["date"],
        "signal": row["signal"],
        "confidence_raw": int(row["confidence"]),
        "confidence": confidence,
        "sentiment": sentiment,
        "n_news": n_news,
        "close": float(row["close"]),
        "stop_loss": float(row["stop_loss"]),
        "take_profit": float(row["take_profit"]),
        "position_pct": float(row["position_pct"]),
        "reasons": row["reasons"].split(" | "),
        "window_days": ncfg["window_days"],
    }


def snapshot(symbol: str, cfg: dict, capital: float, today) -> dict | None:
    """latest_signal + số cổ phiếu gợi ý theo vốn (chỉ dùng trong message Telegram riêng tư)."""
    s = latest_signal(symbol, cfg, today)
    if s is None:
        return None
    s["shares"] = position_shares(capital, s["position_pct"], s["close"], cfg["trading"]["lot_size"])
    s["used_pct"] = s["shares"] * s["close"] / capital
    return s


def _size_line(s: dict) -> str:
    if s["signal"] == "BUY":
        if s["shares"] == 0:
            return "Khối lượng: 0 cp (vốn không đủ 1 lô 100)"
        return f"Khối lượng: {s['shares']:,} cp (≈ {s['used_pct'] * 100:.1f}% vốn, lô 100, bán được từ chiều T+2)"
    if s["signal"] == "SELL":
        return "Khối lượng: bán toàn bộ vị thế đang nắm giữ (nếu có)"
    return "Khối lượng: không giao dịch mới"


def _block(s: dict) -> list[str]:
    return [
        f"Giá đóng cửa (entry tham chiếu): {_fmt(s['close'])}",
        f"Stop-loss: {_fmt(s['stop_loss'])} ({_pct_from(s['stop_loss'], s['close'])})",
        f"Take-profit: {_fmt(s['take_profit'])} ({_pct_from(s['take_profit'], s['close'])})",
        _size_line(s),
        f"Độ tin cậy: {s['confidence']}/100 (kỹ thuật {s['confidence_raw']}, sentiment {s['window_days']} ngày "
        f"{s['sentiment']:+.2f} từ {s['n_news']} tin)",
    ]


def _session(date_str: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")


def change_message(s: dict, prev: str | None) -> str:
    change = f"{LABEL[prev]} → {LABEL[s['signal']]}" if prev else f"{LABEL[s['signal']]} (lần đầu theo dõi)"
    lines = [
        f"{ICON[s['signal']]} VNSignal — {s['symbol']} ({s['exchange']}): {LABEL[s['signal']]}",
        f"Đổi tín hiệu: {change} — phiên {_session(s['date'])}",
        "",
        *_block(s),
        "",
        "Lý do:",
        *[f"• {r}" for r in s["reasons"]],
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


def summary_message(snaps: list[dict], prev: dict) -> str:
    dates = sorted({s["date"] for s in snaps})
    lines = [f"📊 VNSignal — tổng hợp phiên {', '.join(_session(d) for d in dates)}"]
    for s in snaps:
        before = prev.get(s["symbol"], {}).get("signal")
        changed = f" (đổi từ {LABEL[before]})" if before and before != s["signal"] else ""
        lines += ["", f"{ICON[s['signal']]} {s['symbol']} ({s['exchange']}): {LABEL[s['signal']]}{changed}", *_block(s),
                  f"• {s['reasons'][0]}"]
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


def run(cfg: dict, symbols: list[str], state: dict, sender: Sender | None, capital: float, today,
        summary: bool, now_iso: str) -> tuple[dict, int]:
    """Gửi alert, trả về (state mới, số message đã gửi). State của một mã chỉ được cập nhật
    khi message chứa nó gửi thành công → lần sau sẽ thử lại nếu gửi lỗi."""
    snaps = [s for s in (snapshot(sym, cfg, capital, today) for sym in symbols) if s]
    new_state = {k: dict(v) for k, v in state.items()}
    changed = [s for s in snaps if state.get(s["symbol"], {}).get("signal") != s["signal"]]
    sent = 0

    def mark(s):
        new_state[s["symbol"]] = {"signal": s["signal"], "date": s["date"], "confidence": s["confidence"],
                                  "notified_at": now_iso}

    if summary:
        if not snaps or sender is None:
            return new_state, 0
        if sender(summary_message(snaps, state)):
            sent = 1
            for s in changed:
                mark(s)
        return new_state, sent

    if not changed:
        log.info("Không mã nào đổi tín hiệu → không gửi alert")
        return new_state, 0
    for s in changed:
        prev = state.get(s["symbol"], {}).get("signal")
        log.info("%s: %s → %s", s["symbol"], prev or "(chưa có)", s["signal"])
        if sender is not None and sender(change_message(s, prev)):
            sent += 1
            mark(s)
    return new_state, sent

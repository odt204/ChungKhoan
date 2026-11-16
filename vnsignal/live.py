"""Giá tạm tính trong phiên và cảnh báo chạm mức cắt lỗ / chốt lời.

Chỉ đọc nến của phiên đang chạy, không ghi vào data/ohlcv (dữ liệu đó chỉ nhận nến đã đóng phiên)
và không đổi tín hiệu: mức cắt lỗ / chốt lời lấy từ tín hiệu tính theo giá đóng cửa gần nhất.
"""

from datetime import datetime, time, timedelta

from vnsignal.alert import DISCLAIMER, LABEL
from vnsignal.explain import vn_num, vn_pct

EVENT_LABEL = {"SL": "mức cắt lỗ", "TP": "mức chốt lời"}


def _hm(s: str) -> time:
    hh, mm = map(int, s.split(":"))
    return time(hh, mm)


def in_session(now: datetime, cfg: dict) -> bool:
    """Thứ 2–6, trong khung giờ intraday.session_start → session_end (giờ VN)."""
    c = cfg["intraday"]
    return now.weekday() < 5 and _hm(c["session_start"]) <= now.time() <= _hm(c["session_end"])


def fetch_live(source, symbols: list[str], now: datetime) -> dict:
    """{symbol: nến hôm nay + giá đóng cửa phiên trước} cho mã có giao dịch hôm nay; mã chưa có
    nến hôm nay (ngày nghỉ, chưa khớp lệnh) thì vắng mặt."""
    today = now.date().isoformat()
    out = {}
    for symbol in symbols:
        df = source.get_ohlcv(symbol, now.date() - timedelta(days=14), now.date())
        bar, before = df[df["date"] == today], df[df["date"] < today]
        if bar.empty or before.empty:
            continue
        b, prev = bar.iloc[-1], float(before.iloc[-1]["close"])
        out[symbol] = {
            "date": today,
            "at": now.isoformat(timespec="minutes"),
            "price": float(b["close"]), "open": float(b["open"]), "high": float(b["high"]), "low": float(b["low"]),
            "volume": int(b["volume"]),
            "prev_close": prev,
            "change": float(b["close"]) / prev - 1,
        }
    return out


def level_events(live: dict, sig: dict) -> list[tuple[str, float]]:
    """Sự kiện chạm mức trong phiên: ('SL', mức) nếu giá thấp nhất ≤ cắt lỗ, ('TP', mức) nếu giá cao
    nhất ≥ chốt lời. Chỉ xét khi tín hiệu là MUA/GIỮ (BÁN đã là tín hiệu thoát)."""
    if sig["signal"] == "SELL":
        return []
    events = []
    if live["low"] <= sig["stop_loss"]:
        events.append(("SL", float(sig["stop_loss"])))
    if live["high"] >= sig["take_profit"]:
        events.append(("TP", float(sig["take_profit"])))
    return events


def new_events(state: dict | None, today: str, symbol: str, events: list) -> tuple[dict, list]:
    """Lọc sự kiện chưa báo hôm nay. State reset mỗi ngày: {"date", "sent": {symbol: [event...]}}."""
    if not state or state.get("date") != today:
        state = {"date": today, "sent": {}}
    sent = set(state["sent"].get(symbol, []))
    return state, [e for e in events if e[0] not in sent]


def mark_sent(state: dict, symbol: str, event: str) -> None:
    state["sent"].setdefault(symbol, [])
    if event not in state["sent"][symbol]:
        state["sent"][symbol].append(event)


def event_message(symbol: str, event: str, level: float, live: dict, sig: dict) -> str:
    at = datetime.fromisoformat(live["at"]).strftime("%H:%M")
    session = datetime.fromisoformat(sig["date"]).strftime("%d/%m")
    extreme = (f"thấp nhất phiên {vn_num(live['low'])}" if event == "SL" else f"cao nhất phiên {vn_num(live['high'])}")
    advice = ("Nếu đang giữ cổ phiếu này: cân nhắc bán theo kế hoạch cắt lỗ."
              if event == "SL" else "Nếu đang giữ cổ phiếu này: cân nhắc chốt lời một phần hoặc toàn bộ.")
    return "\n".join([
        f"{'⚠️' if event == 'SL' else '🎯'} VNSignal — {symbol} chạm {EVENT_LABEL[event]}",
        f"Giá tạm tính lúc {at}: {vn_num(live['price'])} ({vn_pct(live['change'], 2, sign=True)}), {extreme}",
        f"{EVENT_LABEL[event].capitalize()}: {vn_num(level)} (tính từ giá đóng cửa phiên {session})",
        f"Tín hiệu hiện tại: {LABEL[sig['signal']]} (theo giá đóng cửa, chưa tính phiên hôm nay)",
        "",
        advice + " Giá còn có thể thay đổi đến hết phiên.",
        "",
        DISCLAIMER,
    ])

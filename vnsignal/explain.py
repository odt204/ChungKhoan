"""Diễn giải tín hiệu bằng lời thường cho người mới (dùng trên dashboard).
Chỉ đọc dữ liệu đã tính — không đổi tín hiệu hay điểm số."""

import pandas as pd


def vn_num(x: float, digits: int = 0) -> str:
    """Định dạng số kiểu Việt Nam: 52.700 / 1,5."""
    s = f"{x:,.{digits}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def vn_pct(x, digits: int = 1, sign: bool = False) -> str:
    if x == "inf":
        return "∞"
    if x is None:
        return "–"
    prefix = "+" if sign and x > 0 else ""
    return f"{prefix}{vn_num(x * 100, digits)}%"


def confidence_label(c: int) -> str:
    return "Mạnh" if c >= 60 else "Trung bình" if c >= 30 else "Yếu"


def sentiment_label(s: float | None) -> str:
    if s is None:
        return "Chưa chấm"
    return "Tích cực" if s > 0.15 else "Tiêu cực" if s < -0.15 else "Trung tính"


def sentiment_class(s: float | None) -> str:
    if s is None:
        return "neu"
    return "pos" if s > 0.15 else "neg" if s < -0.15 else "neu"


def plain_reasons(last: pd.Series, cfg: dict) -> list[dict]:
    """4 dòng giải thích (xu hướng, động lượng, dòng tiền, vùng giá) từ chỉ báo của phiên mới nhất.
    Mỗi dòng: {"dir": "up" | "down" | "flat", "title", "text"}."""
    s = cfg["signals"]
    f, m, sl = s["ema"]
    out = []

    above = [n for n, col in [(f, "ema_fast"), (m, "ema_mid"), (sl, "ema_slow")] if last["close"] > last[col]]
    below = [n for n in (f, m, sl) if n not in above]
    if not below:
        out.append({"dir": "up", "title": "Xu hướng tăng",
                    "text": f"Giá đang cao hơn giá trung bình {f}, {m} và {sl} phiên gần nhất."})
    elif not above:
        out.append({"dir": "down", "title": "Xu hướng giảm",
                    "text": f"Giá đang thấp hơn giá trung bình {f}, {m} và {sl} phiên gần nhất."})
    else:
        out.append({"dir": "flat", "title": "Xu hướng chưa rõ",
                    "text": f"Giá cao hơn trung bình {', '.join(map(str, above))} phiên nhưng thấp hơn trung bình "
                            f"{', '.join(map(str, below))} phiên."})

    rsi = last["rsi"]
    r = s["rsi"]
    if last["macd_cross"] == 1:
        mom = ("up", "Đà tăng vừa xuất hiện", "Chỉ báo động lượng MACD vừa chuyển sang tăng.")
    elif last["macd_cross"] == -1:
        mom = ("down", "Đà giảm vừa xuất hiện", "Chỉ báo động lượng MACD vừa chuyển sang giảm.")
    elif rsi < r["oversold"]:
        mom = ("up", "Đã giảm quá mạnh", f"RSI = {vn_num(rsi, 1)} (dưới {r['oversold']}): giá giảm sâu, có thể sắp hồi.")
    elif rsi > r["overbought"]:
        mom = ("down", "Đã tăng quá nóng", f"RSI = {vn_num(rsi, 1)} (trên {r['overbought']}): giá tăng nhanh, dễ điều chỉnh.")
    elif last["macd_hist"] > 0:
        mom = ("up", "Đà tăng nhẹ", f"Lực mua đang nhỉnh hơn lực bán (RSI = {vn_num(rsi, 1)}).")
    else:
        mom = ("down", "Đà giảm nhẹ", f"Lực bán đang nhỉnh hơn lực mua (RSI = {vn_num(rsi, 1)}).")
    out.append(dict(zip(["dir", "title", "text"], mom)))

    ratio = last["volume"] / last["vol_ma"] if last["vol_ma"] else 0
    n = s["volume"]["ma"]
    if ratio >= s["volume"]["spike"] and last["close"] > last["prev_close"]:
        out.append({"dir": "up", "title": "Tiền vào mạnh",
                    "text": f"Khối lượng gấp {vn_num(ratio, 1)} lần trung bình {n} phiên, trong phiên giá tăng."})
    elif ratio >= s["volume"]["spike"] and last["close"] < last["prev_close"]:
        out.append({"dir": "down", "title": "Bị bán mạnh",
                    "text": f"Khối lượng gấp {vn_num(ratio, 1)} lần trung bình {n} phiên, trong phiên giá giảm."})
    else:
        out.append({"dir": "flat", "title": "Giao dịch bình thường",
                    "text": f"Khối lượng bằng {vn_num(ratio, 1)} lần trung bình {n} phiên, chưa có đột biến."})

    w = s["breakout_window"]
    if last["close"] > last["high_n"]:
        out.append({"dir": "up", "title": "Vượt đỉnh gần đây",
                    "text": f"Giá vượt mức cao nhất {w} phiên ({vn_num(last['high_n'])}) — dấu hiệu bứt phá."})
    elif last["close"] < last["low_n"]:
        out.append({"dir": "down", "title": "Thủng đáy gần đây",
                    "text": f"Giá xuống dưới mức thấp nhất {w} phiên ({vn_num(last['low_n'])}) — dấu hiệu suy yếu."})
    else:
        out.append({"dir": "flat", "title": "Đi ngang trong vùng cũ",
                    "text": f"Giá vẫn trong vùng {vn_num(last['low_n'])}–{vn_num(last['high_n'])} của {w} phiên gần nhất."})
    return out


def action(sig: dict, sl_pct: float, tp_pct: float) -> dict:
    """Gợi ý hành động bằng lời thường cho từng loại tín hiệu (tham khảo)."""
    sl, tp = vn_num(sig["stop_loss"]), vn_num(sig["take_profit"])
    if sig["signal"] == "BUY":
        return {
            "title": "Có thể cân nhắc mua",
            "text": f"Các chỉ báo đang ủng hộ chiều tăng. Nếu mua: đặt mức cắt lỗ {sl} ({vn_pct(sl_pct)}), "
                    f"cân nhắc chốt lời quanh {tp} ({vn_pct(tp_pct, sign=True)}), dùng tối đa "
                    f"{vn_pct(sig['position_pct'])} vốn cho mã này. Mua hôm nay thì sớm nhất chiều T+2 mới bán được.",
        }
    if sig["signal"] == "SELL":
        return {
            "title": "Nghiêng về giảm — chưa nên mua",
            "text": "Nếu đang giữ cổ phiếu này: cân nhắc bán bớt hoặc bán hết. "
                    "Nếu chưa có: chưa nên mua, chờ tín hiệu MUA.",
        }
    return {
        "title": "Chưa có tín hiệu rõ — đứng ngoài quan sát",
        "text": f"Đang giữ: có thể giữ tiếp, cân nhắc bán nếu giá xuống dưới {sl} ({vn_pct(sl_pct)}). "
                "Chưa có: nên chờ tín hiệu MUA.",
    }


def backtest_plain(summary: dict | None) -> dict | None:
    """Tóm tắt kiểm định quá khứ bằng lời: làm theo tín hiệu (cấu hình đang dùng) vs mua-và-giữ, 2024 → nay."""
    if not summary:
        return None
    rows = {r.get("key"): r for r in summary["rows"]}
    sig, bh = rows.get("cfg_oos"), rows.get("bh_oos")
    if not sig or not bh:
        return None
    win = sig["cagr"] > bh["cagr"]
    safer = sig["max_drawdown"] > bh["max_drawdown"]
    verdict = (
        f"Làm theo tín hiệu cho kết quả {'TỐT HƠN' if win else 'KÉM HƠN'} mua-và-giữ "
        f"({vn_pct(sig['cagr'], sign=True)}/năm so với {vn_pct(bh['cagr'], sign=True)}/năm)"
        + (", và lúc lỗ sâu nhất nhẹ hơn." if safer else ", và lúc lỗ sâu nhất còn nặng hơn.")
    )
    return {"start": sig["start"], "end": sig["end"], "sig": sig, "bh": bh, "verdict": verdict, "win": win}

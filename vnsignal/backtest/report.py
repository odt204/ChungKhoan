"""Sinh report markdown cho kết quả backtest. Chỉ hiển thị %, không hiển thị số tiền."""

import math

from vnsignal.backtest.walkforward import Run, SymbolBacktest


def _pct(x: float) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.1f}%"


def _pf(x: float) -> str:
    if isinstance(x, float) and math.isnan(x):
        return "–"
    return "∞" if math.isinf(x) else f"{x:.2f}"


def _row(name: str, run: Run) -> str:
    m = run.metrics
    return (
        f"| {name} | {m['start']} → {m['end']} | {m['trades']} | {_pct(m['win_rate'])} | {_pf(m['profit_factor'])} "
        f"| {_pct(m['total_return'])} | {_pct(m['cagr'])} | {_pct(m['max_drawdown'])} | {_pct(m['exposure'])} |"
    )


HEADER = (
    "| Chiến lược | Kỳ | Số lệnh | Win rate | Profit factor | Tổng lợi nhuận | CAGR | Max drawdown | Thời gian nắm giữ |\n"
    "|---|---|---:|---:|---:|---:|---:|---:|---:|"
)


def _weights(w: dict) -> str:
    return ", ".join(f"{k}={v:g}" for k, v in w.items())


def _verdict(strategy: Run, bh: Run) -> str:
    s, b = strategy.metrics, bh.metrics
    ret = "THẮNG" if s["cagr"] > b["cagr"] else "THUA"
    dd = "thấp hơn" if s["max_drawdown"] > b["max_drawdown"] else "cao hơn"
    return (
        f"CAGR {_pct(s['cagr'])} vs buy-and-hold {_pct(b['cagr'])} → **{ret} buy-and-hold** về lợi nhuận; "
        f"max drawdown {_pct(s['max_drawdown'])} ({dd} mức {_pct(b['max_drawdown'])} của buy-and-hold)."
    )


def render(bt: SymbolBacktest, cfg: dict, generated_at: str) -> str:
    t, r, b = cfg["trading"], cfg["risk"], cfg["backtest"]
    ex = cfg["symbols"][bt.symbol]["exchange"]
    limit = cfg["exchanges"][ex]["price_limit"]
    lines = [
        f"# Backtest {bt.symbol}",
        "",
        f"_Sinh lúc {generated_at} (giờ VN) bằng `python -m vnsignal.cli backtest`. Số liệu là output thật của code._",
        "",
        "## Giả định",
        "",
        f"- Dữ liệu: OHLCV daily nguồn VCI, giá **đã điều chỉnh** cổ tức/chia tách; sàn {ex}, biên độ ±{limit * 100:g}%.",
        "- Tín hiệu tính ở giá đóng cửa phiên t, khớp giá mở cửa phiên t+1. Mua bị huỷ nếu phiên khóa trần/không có "
        "giao dịch; bán bị hoãn nếu khóa sàn/không có giao dịch.",
        f"- T+{t['settlement_days']}: mua ngày T chỉ bán từ phiên chiều T+{t['settlement_days']} (khớp ATC ở phiên đó).",
        f"- Phí mua {t['buy_fee'] * 100:g}%, phí bán {t['sell_fee'] * 100:g}% + thuế bán {t['sell_tax'] * 100:g}%; "
        f"lô {t['lot_size']}.",
        f"- Stop-loss = entry − {r['stop_atr']:g}×ATR{r['atr_period']}, take-profit = entry + {r['take_profit_atr']:g}×ATR"
        f"{r['atr_period']}; chạm cả hai cùng phiên → tính SL.",
        f"- Mỗi lệnh tối đa {r['max_position_pct'] * 100:g}% vốn, rủi ro tối đa {r['risk_per_trade_pct'] * 100:g}% vốn. "
        "Phần vốn còn lại để tiền mặt (không lãi). Buy-and-hold dùng 100% vốn → so sánh lợi nhuận "
        "không cùng mức phơi nhiễm; xem thêm cột thời gian nắm giữ và max drawdown.",
        "- Vốn đọc từ `CAPITAL_VND` chỉ để làm tròn lô; report không hiển thị số tiền.",
        "",
        "## Walk-forward",
        "",
        f"Tối ưu trên in-sample {b['in_sample'][0]} → {b['in_sample'][1]} (lưới trọng số {b['weight_grid']}, "
        f"ngưỡng {b['threshold_grid']}, {bt.combos_tested} tổ hợp, hàm mục tiêu CAGR / max(max drawdown, 5%), "
        f"tối thiểu {b['min_trades']} lệnh), kiểm tra out-of-sample từ {b['out_of_sample_start']}.",
        "",
    ]
    if bt.is_opt is None:
        lines += [f"**Không tổ hợp nào đạt tối thiểu {b['min_trades']} lệnh trong in-sample** — bỏ qua walk-forward.", ""]
    else:
        lines += [
            f"Trọng số tối ưu: `{_weights(bt.is_opt.weights)}`, ngưỡng mua/bán ±{bt.is_opt.thresholds[0]:g}.",
            "",
            HEADER,
            _row("Tối ưu — in-sample", bt.is_opt),
            _row("Buy-and-hold — in-sample", bt.bh_is),
            _row("Tối ưu — **out-of-sample**", bt.oos_opt),
            _row("Buy-and-hold — **out-of-sample**", bt.bh_oos),
            "",
            f"**Out-of-sample:** {_verdict(bt.oos_opt, bt.bh_oos)}",
            "",
        ]
    lines += [
        "## Trọng số trong config.yaml (đang dùng cho tín hiệu live)",
        "",
        f"Trọng số: `{_weights(bt.full_cfg.weights)}`, ngưỡng mua {bt.full_cfg.thresholds[0]:g} / "
        f"bán −{bt.full_cfg.thresholds[1]:g}.",
        "",
        HEADER,
        _row("Config — toàn kỳ", bt.full_cfg),
        _row("Buy-and-hold — toàn kỳ", bt.bh_full),
        _row("Config — out-of-sample", bt.oos_cfg),
        _row("Buy-and-hold — out-of-sample", bt.bh_oos),
        "",
        f"**Toàn kỳ:** {_verdict(bt.full_cfg, bt.bh_full)}",
        "",
        f"**Out-of-sample:** {_verdict(bt.oos_cfg, bt.bh_oos)}",
        "",
    ]
    if bt.oos_opt is not None:
        lines += [
            "## Danh sách lệnh out-of-sample (trọng số tối ưu)",
            "",
            "| Mua | Bán | Giá mua | Giá bán | Lợi nhuận (sau phí, thuế) | Lý do thoát |",
            "|---|---|---:|---:|---:|---|",
        ]
        lines += [
            f"| {tr.entry_date} | {tr.exit_date} | {tr.entry_price:,.0f} | {tr.exit_price:,.0f} | {_pct(tr.ret)} | "
            f"{tr.exit_reason} |"
            for tr in bt.oos_opt.result.trades
        ] or ["| – | – | – | – | – | – |"]
        lines.append("")
    lines += ["_Đây là kết quả kiểm định quá khứ, không đảm bảo cho tương lai. Không phải khuyến nghị đầu tư._", ""]
    return "\n".join(lines)

"""Entry point duy nhất: python -m vnsignal.cli <command>."""

import argparse
import logging
import sys
from datetime import date, timedelta

import pandas as pd
from dotenv import load_dotenv

from vnsignal.config import (
    ALERT_STATE_FILE, FUNDAMENTALS_DIR, NEWS_DIR, OHLCV_DIR, REPORTS_DIR, ROOT, SIGNALS_DIR, capital_vnd, load_config, now_vn,
)
from vnsignal.data import get_source
from vnsignal.market import drop_unfinished_bars
from vnsignal.store import read_csv, upsert_csv, write_json

log = logging.getLogger("vnsignal")

EOD_OVERLAP_DAYS = 14  # số ngày lịch tải chồng lên dữ liệu cũ để phát hiện giá điều chỉnh


def _setup_logging() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S%z")
    fmt.converter = lambda *_: now_vn().timetuple()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def _fetch_final(source, cfg: dict, symbol: str, start: date) -> pd.DataFrame:
    now = now_vn()
    df = source.get_ohlcv(symbol, start, now.date())
    exchange = cfg["exchanges"][cfg["symbols"][symbol]["exchange"]]
    return drop_unfinished_bars(df, exchange["close"], cfg["eod_buffer_minutes"], now)


def _summary(symbols: list[str]) -> None:
    for symbol in symbols:
        df = read_csv(OHLCV_DIR / f"{symbol}.csv")
        if df.empty:
            log.info("%s: chưa có dữ liệu", symbol)
        else:
            log.info("%s: %d dòng, %s → %s", symbol, len(df), df["date"].min(), df["date"].max())


def cmd_backfill(cfg: dict, symbols: list[str], force: bool) -> None:
    source = get_source(cfg["data_source"])
    start = date.fromisoformat(cfg["start_date"])
    for symbol in symbols:
        path = OHLCV_DIR / f"{symbol}.csv"
        if not read_csv(path).empty and not force:
            log.info("%s: đã có dữ liệu, bỏ qua backfill (dùng --force để tải lại)", symbol)
            continue
        df = _fetch_final(source, cfg, symbol, start)
        added, changed = upsert_csv(path, df)
        log.info("%s: backfill %s → nay: tải %d nến, thêm %d, cập nhật %d", symbol, start, len(df), added, changed)
    _summary(symbols)


def cmd_eod(cfg: dict, symbols: list[str]) -> None:
    source = get_source(cfg["data_source"])
    tol = cfg["adjustment_tolerance"]
    for symbol in symbols:
        path = OHLCV_DIR / f"{symbol}.csv"
        old = read_csv(path)
        if old.empty:
            raise RuntimeError(f"{symbol}: chưa có dữ liệu, chạy `backfill` trước")
        last = old["date"].max()
        fetched = _fetch_final(source, cfg, symbol, date.fromisoformat(last) - timedelta(days=EOD_OVERLAP_DAYS))

        overlap = fetched.merge(old[["date", "close"]], on="date", suffixes=("", "_old"))
        drift = ((overlap["close"] - overlap["close_old"]).abs() / overlap["close_old"]).max()
        if len(overlap) and drift > tol:
            log.warning("%s: giá cũ lệch %.2f%% (cổ tức/chia tách?) → tải lại toàn bộ lịch sử", symbol, drift * 100)
            fetched = _fetch_final(source, cfg, symbol, date.fromisoformat(cfg["start_date"]))
            added, changed = upsert_csv(path, fetched)
            log.info("%s: tải lại %d nến, thêm %d, cập nhật %d", symbol, len(fetched), added, changed)
            continue

        new = fetched[fetched["date"] > last]
        if new.empty:
            log.info("%s: đã có nến mới nhất %s, bỏ qua", symbol, last)
            continue
        added, _ = upsert_csv(path, new)
        log.info("%s: thêm %d nến (%s)", symbol, added, ", ".join(new["date"]))
    _summary(symbols)


def cmd_fundamentals(cfg: dict, symbols: list[str]) -> None:
    source = get_source(cfg["data_source"])
    for symbol in symbols:
        data = source.get_fundamentals(symbol)
        data["fetched_at"] = now_vn().isoformat(timespec="seconds")
        written = write_json(FUNDAMENTALS_DIR / f"{symbol}.json", data, ignore_keys=("fetched_at",))
        latest = data["ratios_ttm"][-1]
        log.info(
            "%s: %s (Q%s/%s P/E=%.2f P/B=%.2f ROE=%.1f%%)", symbol,
            "đã ghi" if written else "không đổi, bỏ qua",
            latest["quarter"], latest["year"], latest["pe"], latest["pb"], latest["roe"] * 100,
        )


def _load_ohlcv(symbol: str) -> pd.DataFrame:
    df = read_csv(OHLCV_DIR / f"{symbol}.csv")
    if df.empty:
        raise RuntimeError(f"{symbol}: chưa có dữ liệu, chạy `backfill` trước")
    return df


def cmd_signals(cfg: dict, symbols: list[str]) -> None:
    from vnsignal.signals.engine import generate

    for symbol in symbols:
        sig = generate(_load_ohlcv(symbol), cfg, symbol)
        added, changed = upsert_csv(SIGNALS_DIR / f"{symbol}.csv", sig)
        last = sig.iloc[-1]
        log.info(
            "%s %s: %s (điểm %+.2f, tin cậy %d) entry %s SL %s TP %s tỷ trọng %.1f%% vốn — ghi %d mới, %d cập nhật",
            symbol, last["date"], last["signal"], last["score"], last["confidence"],
            f"{last['close']:,}", f"{last['stop_loss']:,}", f"{last['take_profit']:,}",
            last["position_pct"] * 100, added, changed,
        )
        for reason in last["reasons"].split(" | "):
            log.info("    • %s", reason)


def cmd_backtest(cfg: dict, symbols: list[str]) -> None:
    from vnsignal.backtest.report import render, summary
    from vnsignal.backtest.walkforward import backtest_symbol

    capital = capital_vnd()
    REPORTS_DIR.mkdir(exist_ok=True)
    generated = now_vn().strftime("%Y-%m-%d %H:%M")
    for symbol in symbols:
        bt = backtest_symbol(symbol, _load_ohlcv(symbol), cfg, capital)
        path = REPORTS_DIR / f"backtest_{symbol}.md"
        path.write_text(render(bt, cfg, generated), encoding="utf-8", newline="\n")
        write_json(REPORTS_DIR / f"backtest_{symbol}.json", summary(bt, generated))
        log.info("%s → %s (%d tổ hợp)", symbol, path.relative_to(ROOT).as_posix(), bt.combos_tested)
        rows = [("Config toàn kỳ", bt.full_cfg), ("B&H toàn kỳ", bt.bh_full)]
        if bt.is_opt:
            rows = [("Tối ưu IS", bt.is_opt), ("B&H IS", bt.bh_is), ("Tối ưu OOS", bt.oos_opt)] + rows
        rows += [("Config OOS", bt.oos_cfg), ("B&H OOS", bt.bh_oos)]
        for name, run in rows:
            m = run.metrics
            log.info(
                "    %-15s %s→%s lệnh=%3d win=%5.1f%% PF=%5s CAGR=%6.1f%% MDD=%6.1f%% nắm giữ=%5.1f%%",
                name, m["start"], m["end"], m["trades"], m["win_rate"] * 100, f"{m['profit_factor']:.2f}",
                m["cagr"] * 100, m["max_drawdown"] * 100, m["exposure"] * 100,
            )
        if bt.is_opt:
            log.info("    Trọng số tối ưu: %s, ngưỡng ±%g", bt.is_opt.weights, bt.is_opt.thresholds[0])


def cmd_news(cfg: dict, symbols: list[str]) -> None:
    from vnsignal.news import collect, fetch_rss
    from vnsignal.sentiment import adjust_confidence, aggregate, score_pending
    from vnsignal.store import merge_jsonl, read_jsonl, write_jsonl

    ncfg = cfg["news"]
    source = get_source(cfg["data_source"])
    rss = fetch_rss(ncfg["rss"])
    sources_ok = bool(rss)
    for symbol in symbols:
        try:
            adapter_items = source.get_news(symbol)
            sources_ok = True
        except Exception as e:  # noqa: BLE001
            log.warning("%s: lỗi lấy tin từ %s: %s", symbol, source.name, e)
            adapter_items = []
        path = NEWS_DIR / f"{symbol}.jsonl"
        added = merge_jsonl(path, collect(symbol, cfg["symbols"][symbol], adapter_items, rss))
        records = read_jsonl(path)
        scored = score_pending(records, symbol, cfg)
        if scored:
            write_jsonl(path, records)
        sentiment, n = aggregate(records, now_vn().date(), ncfg["window_days"])
        unscored = sum(r["sentiment"] is None for r in records)
        log.info(
            "%s: +%d tin mới (tổng %d), chấm %d, chưa chấm %d | sentiment %d ngày = %+.2f (%d tin)",
            symbol, added, len(records), scored, unscored, ncfg["window_days"], sentiment, n,
        )
        signals = read_csv(SIGNALS_DIR / f"{symbol}.csv")
        if not signals.empty:
            last = signals.iloc[-1]
            adj = adjust_confidence(last["signal"], int(last["confidence"]), sentiment, ncfg["max_confidence_adjust"])
            log.info("    tín hiệu %s %s: confidence %d → %d sau sentiment", last["date"], last["signal"],
                     last["confidence"], adj)
        for r in sorted(records, key=lambda r: r.get("published_at") or "", reverse=True)[:3]:
            score = "  –  " if r["sentiment"] is None else f"{r['sentiment']:+.2f}"
            log.info("    [%s] %s %s: %s", score, (r.get("published_at") or "")[:10], r["source"], r["title"][:90])
    if not sources_ok:
        raise RuntimeError("Mọi nguồn tin đều lỗi")


def cmd_alert(cfg: dict, symbols: list[str], summary: bool) -> None:
    from vnsignal import alert
    from vnsignal.store import read_json

    path = ALERT_STATE_FILE
    state = read_json(path) or {}
    sender = alert.telegram_sender()
    now = now_vn()
    new_state, sent = alert.run(
        cfg, symbols, state, sender, capital_vnd(), now.date(), summary, now.isoformat(timespec="seconds")
    )
    written = write_json(path, new_state)
    log.info("Alert%s: đã gửi %d message, alert_state %s", " (tổng hợp)" if summary else "", sent,
             "cập nhật" if written else "không đổi")


def cmd_build_site(cfg: dict) -> None:
    from vnsignal.sitebuilder import SITE_DIR, build

    now = now_vn()
    written = build(cfg, SITE_DIR, now.date(), now.strftime("%H:%M %d/%m/%Y"))
    total_kb = sum(p.stat().st_size for p in written) / 1024
    log.info("build-site: %d file, %.0f KB → %s", len(written), total_kb, SITE_DIR.relative_to(ROOT).as_posix())
    for p in written:
        log.info("    %s (%.0f KB)", p.relative_to(ROOT).as_posix(), p.stat().st_size / 1024)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    _setup_logging()
    cfg = load_config()

    parser = argparse.ArgumentParser(prog="python -m vnsignal.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in [
        ("backfill", f"Nạp lịch sử OHLCV từ {cfg['start_date']} cho mã chưa có dữ liệu"),
        ("eod", "Lấy nến ngày mới nhất (bỏ qua nếu đã có)"),
        ("fundamentals", "Cập nhật thông tin cơ bản + chỉ số tài chính"),
        ("signals", "Tính tín hiệu BUY/SELL/HOLD, ghi data/signals/{symbol}.csv"),
        ("backtest", "Backtest walk-forward, ghi reports/backtest_{symbol}.md"),
        ("news", "Thu thập tin (VCI + RSS CafeF/Vietstock), chấm sentiment, ghi data/news/{symbol}.jsonl"),
        ("alert", "Gửi Telegram khi tín hiệu đổi trạng thái (so với data/alert_state.json)"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--symbols", nargs="+", choices=list(cfg["symbols"]), default=list(cfg["symbols"]))
        if name == "backfill":
            p.add_argument("--force", action="store_true", help="Tải lại toàn bộ kể cả khi đã có dữ liệu")
        if name == "alert":
            p.add_argument("--summary", action="store_true", help="Gửi bản tổng hợp mọi mã dù tín hiệu không đổi")
    sub.add_parser("build-site", help="Sinh dashboard tĩnh vào site/ (mở được bằng file://)")
    args = parser.parse_args(argv)

    try:
        if args.command == "backfill":
            cmd_backfill(cfg, args.symbols, args.force)
        elif args.command == "eod":
            cmd_eod(cfg, args.symbols)
        elif args.command == "fundamentals":
            cmd_fundamentals(cfg, args.symbols)
        elif args.command == "signals":
            cmd_signals(cfg, args.symbols)
        elif args.command == "backtest":
            cmd_backtest(cfg, args.symbols)
        elif args.command == "news":
            cmd_news(cfg, args.symbols)
        elif args.command == "alert":
            cmd_alert(cfg, args.symbols, args.summary)
        elif args.command == "build-site":
            cmd_build_site(cfg)
    except Exception:
        log.exception("Lệnh `%s` lỗi", args.command)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

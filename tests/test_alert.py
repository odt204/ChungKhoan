import logging
from datetime import date

import pandas as pd
import pytest

from vnsignal import alert
from vnsignal.config import load_config
from vnsignal.store import write_jsonl

CFG = load_config()
TODAY = date(2026, 10, 30)
CAPITAL = 100_000_000


@pytest.fixture
def data_dirs(tmp_path, monkeypatch):
    sig_dir, news_dir = tmp_path / "signals", tmp_path / "news"
    sig_dir.mkdir()
    monkeypatch.setattr(alert, "SIGNALS_DIR", sig_dir)
    monkeypatch.setattr(alert, "NEWS_DIR", news_dir)

    def set_signal(symbol, signal, close=52_700, sl=49_694, tp=57_209, pct=0.0, confidence=64):
        pd.DataFrame([{
            "date": "2026-10-29", "close": close, "score": 0.5, "signal": signal, "confidence": confidence,
            "stop_loss": sl, "take_profit": tp, "position_pct": pct,
            "reasons": "Lý do 1 | Lý do 2 | Lý do 3",
        }]).to_csv(sig_dir / f"{symbol}.csv", index=False)

    return set_signal, news_dir


class Recorder:
    def __init__(self, ok=True):
        self.messages, self.ok = [], ok

    def __call__(self, text):
        self.messages.append(text)
        return self.ok


def run(state, sender, summary=False, symbols=("FPT",)):
    return alert.run(CFG, list(symbols), state, sender, CAPITAL, TODAY, summary, "2026-10-30T15:20:00+07:00")


def test_alert_sends_once_when_signal_unchanged(data_dirs):
    set_signal, _ = data_dirs
    set_signal("FPT", "SELL")
    sender = Recorder()
    state, sent = run({}, sender)
    assert sent == 1 and state["FPT"]["signal"] == "SELL"
    state2, sent2 = run(state, sender)
    assert sent2 == 0 and state2 == state
    assert len(sender.messages) == 1


def test_alert_sends_on_state_change(data_dirs):
    set_signal, _ = data_dirs
    set_signal("FPT", "BUY", close=10_000, sl=8_000, tp=13_000, pct=0.10, confidence=60)
    sender = Recorder()
    state, sent = run({"FPT": {"signal": "HOLD"}}, sender)
    assert sent == 1 and state["FPT"]["signal"] == "BUY"
    msg = sender.messages[0]
    assert "GIỮ → MUA" in msg
    assert "Khối lượng: 1,000 cp" in msg           # 10% × 100tr / 10.000 = 1.000 cp, bội số lô 100
    assert "Stop-loss: 8,000 (-20.0%)" in msg and "Take-profit: 13,000 (+30.0%)" in msg
    assert msg.rstrip().endswith("Đây là tín hiệu tham khảo, không phải khuyến nghị đầu tư.")


def test_failed_send_keeps_old_state_for_retry(data_dirs):
    set_signal, _ = data_dirs
    set_signal("FPT", "SELL")
    state, sent = run({"FPT": {"signal": "HOLD"}}, Recorder(ok=False))
    assert sent == 0 and state["FPT"]["signal"] == "HOLD"


def test_missing_telegram_env_warns_and_does_not_fail(data_dirs, monkeypatch, caplog):
    set_signal, _ = data_dirs
    set_signal("FPT", "SELL")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with caplog.at_level(logging.WARNING, logger="vnsignal"):
        sender = alert.telegram_sender()
    assert sender is None and "TELEGRAM_BOT_TOKEN" in caplog.text
    state, sent = run({}, sender)
    assert sent == 0 and state == {}


def test_summary_sends_even_without_change(data_dirs):
    set_signal, _ = data_dirs
    for sym in ["FPT", "ACV", "HVN"]:
        set_signal(sym, "HOLD")
    sender = Recorder()
    prev = {s: {"signal": "HOLD"} for s in ["FPT", "ACV", "HVN"]}
    state, sent = run(prev, sender, summary=True, symbols=["FPT", "ACV", "HVN"])
    assert sent == 1 and state == prev
    msg = sender.messages[0]
    assert all(f"{s} (" in msg for s in ["FPT", "ACV", "HVN"])
    assert msg.rstrip().endswith("không phải khuyến nghị đầu tư.")


def test_summary_marks_changes_and_updates_state(data_dirs):
    set_signal, _ = data_dirs
    set_signal("FPT", "SELL")
    sender = Recorder()
    state, _ = run({"FPT": {"signal": "HOLD"}}, sender, summary=True)
    assert "(đổi từ GIỮ)" in sender.messages[0]
    assert state["FPT"]["signal"] == "SELL"


def test_sentiment_adjusts_confidence_in_message(data_dirs):
    set_signal, news_dir = data_dirs
    set_signal("FPT", "SELL", confidence=64)
    write_jsonl(news_dir / "FPT.jsonl", [
        {"key": "a", "sentiment": -1.0, "published_at": "2026-10-29T10:00:00+07:00"},
        {"key": "b", "sentiment": 0.0, "published_at": "2026-10-28T10:00:00+07:00"},
    ])
    sender = Recorder()
    run({}, sender)
    assert "Độ tin cậy: 69/100 (kỹ thuật 64, sentiment 3 ngày -0.50 từ 2 tin)" in sender.messages[0]


def test_telegram_sender_posts_and_hides_token(monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:SECRET")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    calls = []

    class Resp:
        status_code = 401

        def json(self):
            return {"ok": False, "description": "Unauthorized"}

    def fake_post(url, json, timeout):
        calls.append((url, json))
        return Resp()

    monkeypatch.setattr(alert.requests, "post", fake_post)
    with caplog.at_level(logging.WARNING, logger="vnsignal"):
        assert alert.telegram_sender()("xin chào") is False
    assert calls[0][0] == "https://api.telegram.org/bot123:SECRET/sendMessage"
    assert calls[0][1]["chat_id"] == "42" and calls[0][1]["text"] == "xin chào"
    assert "SECRET" not in caplog.text and "401" in caplog.text

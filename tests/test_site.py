import json
import re
from datetime import date

import pandas as pd

from vnsignal.config import load_config
from vnsignal.sitebuilder import CHART_LIB, build, signal_changes

CFG = load_config()


def test_signal_changes_only_on_transitions():
    sig = pd.DataFrame({
        "date": ["d1", "d2", "d3", "d4", "d5"],
        "signal": ["HOLD", "BUY", "BUY", "HOLD", "SELL"],
        "close": [1, 2, 3, 4, 5], "confidence": [0, 50, 60, 10, 70],
    })
    assert [(c["date"], c["from"], c["to"]) for c in signal_changes(sig)] == [
        ("d2", "HOLD", "BUY"), ("d4", "BUY", "HOLD"), ("d5", "HOLD", "SELL"),
    ]


def test_build_site_from_committed_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPITAL_VND", "987654321")
    out = tmp_path / "site"
    build(CFG, out, date(2026, 10, 30), "15:20 30/10/2026")

    index = (out / "index.html").read_text(encoding="utf-8")
    assert index.count('class="card signal-') == 3
    assert 'href="huong-dan.html"' in index and (out / "huong-dan.html").exists()
    assert "Giá đóng cửa phiên" in index
    assert "Đây là tín hiệu tham khảo, không phải khuyến nghị đầu tư." in index
    assert 'href="assets/site.css"' in index  # đường dẫn tương đối → chạy được với file://

    for symbol in CFG["symbols"]:
        page = (out / f"{symbol}.html").read_text(encoding="utf-8")
        data = json.loads((out / "data" / f"{symbol}.json").read_text(encoding="utf-8"))
        # dữ liệu chart nhúng trong trang (file:// không fetch được JSON) và trùng với file data/
        embedded = re.search(r'<script type="application/json" id="chart-data">(.*?)</script>', page, re.S).group(1)
        assert json.loads(embedded) == data
        assert CHART_LIB in page and "fetch(" not in (out / "assets" / "chart.js").read_text(encoding="utf-8")
        n = len(data["t"])
        assert all(len(data[k]) == n for k in ["o", "h", "l", "c", "v", "ema_fast", "rsi", "macd", "atr"])
        assert all(m["s"] in ("BUY", "SELL") for m in data["markers"])
        assert "Nếu làm theo tín hiệu trước đây thì sao?" in page and "Tin tức gần đây" in page
        assert "Vì sao?" in page and 'class="callout"' in page

    # Không lộ vốn / số tiền tuyệt đối
    for f in out.rglob("*"):
        if f.is_file():
            text = f.read_text(encoding="utf-8")
            assert "987654321" not in text and "987.654.321" not in text and " cp " not in text

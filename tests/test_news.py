import json
import logging
from datetime import date
from types import SimpleNamespace

from vnsignal.config import load_config
from vnsignal.news import collect, matches_symbol, news_key, parse_rss
from vnsignal.sentiment import adjust_confidence, aggregate, score_pending
from vnsignal.store import merge_jsonl, read_jsonl, write_jsonl

CFG = load_config()

RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item><title>FPT lãi 9 tháng tăng 20%</title><link>https://cafef.vn/fpt-lai.chn</link>
<description><![CDATA[<a href="x"><img src="y"/></a>FPT báo lãi &amp; doanh thu tăng]]></description>
<pubDate>Fri, 30 Oct 26 09:46:00 +0700</pubDate></item>
<item><title>FPT Retail mở thêm 100 nhà thuốc</title><link>https://cafef.vn/frt.chn</link>
<description>Chuỗi Long Châu</description><pubDate>Thu, 29 Oct 2026 08:00:00 +0700</pubDate></item>
<item><title>Vietnam Airlines nhận thêm máy bay</title><link>http://vietstock.vn/hvn.htm</link>
<description></description><pubDate>Wed, 28 Oct 2026 20:00:00 GMT</pubDate></item>
</channel></rss>""".encode()


def test_parse_rss_cleans_html_and_converts_timezone():
    items = parse_rss(RSS, "CafeF")
    assert len(items) == 3
    assert items[0]["summary"] == "FPT báo lãi & doanh thu tăng"
    assert items[0]["published_at"] == "2026-10-30T09:46:00+07:00"
    assert items[2]["published_at"] == "2026-10-29T03:00:00+07:00"  # GMT → giờ VN


def test_symbol_filter_respects_excludes():
    items = parse_rss(RSS, "CafeF")
    fpt = CFG["symbols"]["FPT"]
    assert [matches_symbol(i, fpt) for i in items] == [True, False, False]
    assert matches_symbol(items[2], CFG["symbols"]["HVN"])
    assert not matches_symbol(items[0], CFG["symbols"]["ACV"])


def test_dedupe_by_url_hash_across_feeds_and_runs(tmp_path):
    items = parse_rss(RSS, "CafeF")
    dup = dict(items[2], url="https://vietstock.vn/hvn.htm", source="Vietstock")  # cùng bài, khác scheme
    recs = collect("HVN", CFG["symbols"]["HVN"], [], items + [dup])
    assert len(recs) == 1
    assert news_key("http://vietstock.vn/hvn.htm", "x") == news_key("https://vietstock.vn/hvn.htm", "y")

    path = tmp_path / "HVN.jsonl"
    assert merge_jsonl(path, recs) == 1
    assert merge_jsonl(path, collect("HVN", CFG["symbols"]["HVN"], [], items)) == 0
    assert len(read_jsonl(path)) == 1


def test_adapter_news_without_url_dedupes_by_id(tmp_path):
    vci = [{"id": "vci:1", "title": "FPT: Nghị quyết HĐQT", "published_at": "2026-10-28T18:03:26+07:00",
            "url": None, "source": "VCI"}]
    path = tmp_path / "FPT.jsonl"
    assert merge_jsonl(path, collect("FPT", CFG["symbols"]["FPT"], vci, [])) == 1
    assert merge_jsonl(path, collect("FPT", CFG["symbols"]["FPT"], vci, [])) == 0


def test_merge_keeps_existing_sentiment(tmp_path):
    path = tmp_path / "FPT.jsonl"
    recs = collect("FPT", CFG["symbols"]["FPT"], [], parse_rss(RSS, "CafeF"))
    merge_jsonl(path, recs)
    stored = read_jsonl(path)
    stored[0]["sentiment"] = 0.6
    write_jsonl(path, stored)
    merge_jsonl(path, collect("FPT", CFG["symbols"]["FPT"], [], parse_rss(RSS, "CafeF")))
    assert read_jsonl(path)[0]["sentiment"] == 0.6


def test_no_api_key_skips_scoring(monkeypatch, caplog):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    recs = collect("FPT", CFG["symbols"]["FPT"], [], parse_rss(RSS, "CafeF"))
    with caplog.at_level(logging.WARNING, logger="vnsignal"):
        assert score_pending(recs, "FPT", CFG) == 0
    assert recs[0]["sentiment"] is None
    assert "ANTHROPIC_API_KEY" in caplog.text


class FakeClient:
    def __init__(self, payload, stop_reason="end_turn"):
        self.calls = []
        self.payload, self.stop_reason = payload, stop_reason
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        block = SimpleNamespace(type="text", text=json.dumps(self.payload))
        return SimpleNamespace(stop_reason=self.stop_reason, content=[block])


def test_score_pending_maps_and_clamps_scores():
    recs = collect("HVN", CFG["symbols"]["HVN"], [], parse_rss(RSS, "CafeF"))
    client = FakeClient({"items": [{"index": 0, "score": 1.7, "reason": "Mở rộng đội bay"},
                                   {"index": 5, "score": -1, "reason": "index sai"}]})
    assert score_pending(recs, "HVN", CFG, client=client) == 1
    assert recs[0]["sentiment"] == 1.0
    assert recs[0]["sentiment_model"] == CFG["news"]["sentiment_model"]
    call = client.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["output_config"]["effort"] == "low"
    assert not {"temperature", "top_p", "top_k", "thinking"} & call.keys()
    assert "Vietnam Airlines" in call["messages"][0]["content"]


def test_score_pending_skips_truncated_response():
    recs = collect("HVN", CFG["symbols"]["HVN"], [], parse_rss(RSS, "CafeF"))
    client = FakeClient({"items": []}, stop_reason="max_tokens")
    assert score_pending(recs, "HVN", CFG, client=client) == 0
    assert recs[0]["sentiment"] is None


def test_aggregate_window():
    recs = [
        {"sentiment": 0.8, "published_at": "2026-10-30T09:00:00+07:00"},
        {"sentiment": -0.2, "published_at": "2026-10-28T23:30:00+07:00"},
        {"sentiment": 1.0, "published_at": "2026-10-27T10:00:00+07:00"},  # ngoài cửa sổ 3 ngày
        {"sentiment": None, "published_at": "2026-10-30T10:00:00+07:00"},
    ]
    assert aggregate(recs, date(2026, 10, 30), 3) == (0.3, 2)
    assert aggregate([], date(2026, 10, 30), 3) == (0.0, 0)


def test_sentiment_is_only_a_bounded_modifier():
    assert adjust_confidence("BUY", 60, 1.0, 10) == 70
    assert adjust_confidence("BUY", 60, -0.5, 10) == 55
    assert adjust_confidence("SELL", 60, -1.0, 10) == 70   # tin xấu củng cố SELL
    assert adjust_confidence("SELL", 60, 1.0, 10) == 50
    assert adjust_confidence("HOLD", 20, 1.0, 10) == 20    # không tạo tín hiệu
    assert adjust_confidence("BUY", 95, 1.0, 10) == 100

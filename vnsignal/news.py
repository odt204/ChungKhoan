"""Thu thập tin tức: adapter (VCI) + RSS CafeF/Vietstock lọc theo mã, dedupe theo URL hash."""

import hashlib
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests

from vnsignal.config import TZ, now_vn

log = logging.getLogger("vnsignal")

SUMMARY_CHARS = 400
USER_AGENT = "Mozilla/5.0 (compatible; VNSignal/0.1)"


def news_key(url: str | None, fallback_id: str) -> str:
    """Khoá dedupe: hash URL (chuẩn hoá http→https, bỏ khoảng trắng). Tin không có URL
    (VCI chỉ trả news_id) dùng id của nguồn."""
    basis = url.strip().replace("http://", "https://", 1) if url else fallback_id
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _clean(text: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_rss(xml_bytes: bytes, source: str) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.findall("./channel/item"):
        url = (it.findtext("link") or "").strip()
        title = _clean(it.findtext("title"))
        if not url or not title:
            continue
        pub = it.findtext("pubDate")
        published = parsedate_to_datetime(pub).astimezone(TZ) if pub else None
        items.append({
            "url": url,
            "title": title,
            "summary": _clean(it.findtext("description"))[:SUMMARY_CHARS],
            "published_at": published.isoformat() if published else None,
            "source": source,
        })
    return items


def fetch_rss(feeds: list[dict]) -> list[dict]:
    """Tải tất cả feed; feed lỗi được log và bỏ qua."""
    items = []
    for feed in feeds:
        try:
            r = requests.get(feed["url"], headers={"User-Agent": USER_AGENT}, timeout=20)
            r.raise_for_status()
            got = parse_rss(r.content, feed["source"])
            log.info("RSS %s: %d tin (%s)", feed["source"], len(got), feed["url"])
            items += got
        except Exception as e:  # noqa: BLE001 — một feed lỗi không làm hỏng cả lệnh
            log.warning("RSS lỗi %s: %s", feed["url"], e)
    return items


def matches_symbol(item: dict, symbol_cfg: dict) -> bool:
    text = f"{item['title']} {item.get('summary', '')}"
    for phrase in symbol_cfg.get("news_exclude", []):
        text = text.replace(phrase, " ")
    return any(re.search(p, text) for p in symbol_cfg.get("news_match", []))


def to_record(item: dict, fallback_id: str, fetched_at: datetime | None = None) -> dict:
    return {
        "key": news_key(item.get("url"), fallback_id),
        "url": item.get("url"),
        "title": item["title"],
        "summary": item.get("summary", ""),
        "published_at": item.get("published_at"),
        "source": item["source"],
        "fetched_at": (fetched_at or now_vn()).isoformat(timespec="seconds"),
        "sentiment": None,
        "sentiment_reason": None,
        "sentiment_model": None,
    }


def collect(symbol: str, symbol_cfg: dict, adapter_items: list[dict], rss_items: list[dict]) -> list[dict]:
    """Gộp tin adapter (đã theo mã) + tin RSS khớp mã; dedupe theo key trong lô."""
    fetched_at = now_vn()
    records = {}
    for item in adapter_items:
        rec = to_record(item, item["id"], fetched_at)
        records.setdefault(rec["key"], rec)
    for item in rss_items:
        if matches_symbol(item, symbol_cfg):
            rec = to_record(item, item["url"], fetched_at)
            records.setdefault(rec["key"], rec)
    return list(records.values())

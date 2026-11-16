"""Nguồn VCI (Vietcap): gọi thẳng endpoint công khai bằng requests.

Trước đây đi qua vnstock 4.0.9; từ 10/11/2026 kênh cài vnstock cũ bị gỡ (HTTP 410) và thế hệ 6
chuyển sang Open API có khoá, nên adapter gọi trực tiếp các endpoint mà vnstock 4.x đã dùng.
Hành vi thật đã verify (scripts/smoke_vci.py):
- gap-chart trả mảng cột t/o/h/l/c/v; giá theo ĐỒNG, đã điều chỉnh cổ tức/chia tách; t là unix giây
  (00:00 UTC của ngày giao dịch). Có cả nến của phiên đang chạy.
- countBack đếm theo số nến, nên có thể trả thừa phiên trước `start` → phải lọc lại.
- Tin tức không có URL bài viết, chỉ có newsId, newsTitle, publicDate (giờ VN).
"""

import re
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

from vnsignal.config import TZ
from vnsignal.data.base import OHLCV_COLUMNS, MarketDataSource

CHART_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
IQ_URL = "https://iq.vietcap.com.vn/api/iq-insight-service/v1"
# Endpoint chỉ trả dữ liệu cho request có Referer/Origin của trang Vietcap (giống trình duyệt).
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/152.0.0.0 Safari/537.36",
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn/",
}
TIMEOUT = 20
RETRIES = 2

OVERVIEW_FIELDS = [
    "organ_name", "sector", "listing_date", "current_price", "market_cap", "issue_share",
    "free_float_percentage", "foreigner_percentage", "maximum_foreign_percentage",
    "highest_price1_year", "lowest_price1_year", "rating", "target_price",
    "upside_to_target_percent",
]
RATIO_FIELDS = [
    "year", "quarter", "pe", "pb", "ps", "ev_to_ebitda", "roe", "roa", "roic",
    "gross_margin", "after_tax_profit_margin", "debt_to_equity", "current_ratio",
    "dividend_yield", "market_cap",
]
RATIO_QUARTERS = 8
NEWS_PAGE_SIZE = 50


def camel_to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def parse_gap_chart(payload: list, start: date, end: date) -> pd.DataFrame:
    """Mảng cột gap-chart → OHLCV chuẩn, lọc đúng [start, end], bỏ trùng ngày, sort."""
    if not payload or not isinstance(payload, list) or not payload[0].get("t"):
        return pd.DataFrame(columns=OHLCV_COLUMNS)
    d = payload[0]
    df = pd.DataFrame({
        "date": [datetime.fromtimestamp(int(t), timezone.utc).strftime("%Y-%m-%d") for t in d["t"]],
        "open": d["o"], "high": d["h"], "low": d["l"], "close": d["c"], "volume": d["v"],
    })
    df = df[(df["date"] >= start.isoformat()) & (df["date"] <= end.isoformat())]
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float).round().astype("int64")
    df["volume"] = df["volume"].astype("int64")
    return df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


class VCISource(MarketDataSource):
    name = "VCI"

    def __init__(self, session: requests.Session | None = None):
        self.http = session or requests.Session()
        self.http.headers.update(HEADERS)

    def _request(self, method: str, url: str, **kw):
        last = None
        for attempt in range(RETRIES + 1):
            try:
                r = self.http.request(method, url, timeout=TIMEOUT, **kw)
                r.raise_for_status()
                return r.json()
            except (requests.ConnectionError, requests.Timeout) as e:
                last = e
                time.sleep(2 * (attempt + 1))
        raise last

    def _iq(self, path: str):
        body = self._request("GET", f"{IQ_URL}/{path}")
        if not isinstance(body, dict) or not body.get("successful"):
            raise ValueError(f"VCI trả lỗi cho {path}: {str(body)[:200]}")
        return body["data"]

    def get_ohlcv(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        bars = len(pd.bdate_range(start, end)) + 5
        to = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp())
        payload = self._request("POST", CHART_URL, json={
            "timeFrame": "ONE_DAY", "symbols": [symbol], "to": to, "countBack": bars,
        })
        return parse_gap_chart(payload, start, end)

    def get_fundamentals(self, symbol: str) -> dict:
        details = self._iq(f"company/details?ticker={symbol}")
        stats = self._iq(f"company/{symbol}/statistics-financial")
        if not details or not stats:
            raise ValueError(f"VCI trả fundamentals rỗng cho {symbol}")
        overview = {camel_to_snake(k): v for k, v in details.items()}
        overview["organ_name"] = details.get("viOrganName") or details.get("organName")
        rows = []
        for raw in stats:
            row = {camel_to_snake(k): v for k, v in raw.items()}
            row["year"], row["quarter"] = int(row["year"]), int(row["quarter"])
            rows.append({k: row.get(k) for k in RATIO_FIELDS})
        rows = sorted(rows, key=lambda r: (r["year"], r["quarter"]))[-RATIO_QUARTERS:]
        return {
            "symbol": symbol,
            "source": self.name,
            "overview": {k: overview.get(k) for k in OVERVIEW_FIELDS},
            "ratios_ttm": rows,
        }

    def get_news(self, symbol: str) -> list[dict]:
        today = datetime.now(TZ).date()
        page = self._iq(f"news?ticker={symbol}&fromDate={today.year - 1}0101&toDate={today:%Y%m%d}"
                        f"&languageId=1&page=0&size={NEWS_PAGE_SIZE}")
        items = []
        for row in page.get("content") or []:
            if not row.get("newsTitle") or not row.get("publicDate"):
                continue
            items.append({
                "id": f"vci:{row['newsId']}",
                "title": row["newsTitle"],
                "published_at": pd.Timestamp(row["publicDate"]).tz_localize(TZ).isoformat(),
                "url": row.get("newsSourceLink"),
                "source": self.name,
            })
        return items

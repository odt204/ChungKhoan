"""Nguồn VCI (Vietcap) qua vnstock 4.0.9.

Hành vi thật đã verify bằng scripts/smoke_vci.py:
- Quote.history trả giá theo NGHÌN đồng (close 52.7 ↔ overview current_price 52700).
- Quote.history(start=...) trả thừa vài phiên trước start → phải lọc lại.
- Giá lịch sử là giá đã điều chỉnh (cổ tức/chia tách).
- Company.news không có URL bài viết, chỉ có news_id, news_title, public_date.
"""

import json
import os
from datetime import date

import pandas as pd

from vnsignal.config import TZ
from vnsignal.data.base import OHLCV_COLUMNS, MarketDataSource

# Tắt telemetry tuỳ chọn của vnai trước khi vnstock được import.
os.environ.setdefault("VNSTOCK_TELEMETRY", "0")

PRICE_UNIT = 1000  # VCI trả giá theo nghìn đồng

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


def normalize_ohlcv(raw: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Chuẩn hoá output Quote.history: đổi sang VND, lọc đúng [start, end], bỏ trùng ngày."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)
    df = raw.rename(columns={"time": "date"})[OHLCV_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[(df["date"] >= start.isoformat()) & (df["date"] <= end.isoformat())]
    for col in ["open", "high", "low", "close"]:
        df[col] = (df[col].astype(float) * PRICE_UNIT).round().astype("int64")
    df["volume"] = df["volume"].astype("int64")
    df = df.drop_duplicates("date", keep="last").sort_values("date")
    return df.reset_index(drop=True)


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame → list dict JSON-serializable (NaN → None, numpy → python)."""
    df = df.loc[:, ~df.columns.duplicated()]
    return json.loads(df.to_json(orient="records", force_ascii=False, date_format="iso"))


class VCISource(MarketDataSource):
    name = "VCI"

    def get_ohlcv(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        from vnstock import Quote

        raw = Quote(source="VCI", symbol=symbol).history(
            start=start.isoformat(), end=end.isoformat(), interval="1D"
        )
        return normalize_ohlcv(raw, start, end)

    def get_fundamentals(self, symbol: str) -> dict:
        from vnstock import Company

        company = Company(source="VCI", symbol=symbol)
        overview = _records(company.overview())
        ratios = company.ratio_summary()
        if not overview or ratios.empty:
            raise ValueError(f"VCI trả fundamentals rỗng cho {symbol}")
        ratios = ratios.sort_values(["year", "quarter"]).tail(RATIO_QUARTERS)
        ratios = ratios[[c for c in RATIO_FIELDS if c in ratios.columns]]
        return {
            "symbol": symbol,
            "source": self.name,
            "overview": {k: overview[0].get(k) for k in OVERVIEW_FIELDS},
            "ratios_ttm": _records(ratios),
        }

    def get_news(self, symbol: str) -> list[dict]:
        from vnstock import Company

        df = Company(source="VCI", symbol=symbol).news()
        if df.empty:
            return []
        items = []
        for row in _records(df):
            published = pd.Timestamp(row["public_date"]).tz_localize(TZ)
            items.append({
                "id": f"vci:{row['news_id']}",
                "title": row["news_title"],
                "published_at": published.isoformat(),
                "url": row.get("news_source_link"),
                "source": self.name,
            })
        return items

"""Interface nguồn dữ liệu thị trường. Mỗi nguồn (VCI, ...) implement class này
để có thể đổi nguồn mà không sửa phần còn lại của hệ thống."""

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

# Cột chuẩn của OHLCV daily. date: "YYYY-MM-DD" (ngày giao dịch VN),
# giá: VND (đã điều chỉnh theo nguồn), volume: cổ phiếu.
OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


class MarketDataSource(ABC):
    name: str

    @abstractmethod
    def get_ohlcv(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Nến ngày trong [start, end], cột OHLCV_COLUMNS, sort theo date."""

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> dict:
        """Thông tin cơ bản + chỉ số tài chính gần nhất, JSON-serializable."""

    @abstractmethod
    def get_news(self, symbol: str) -> list[dict]:
        """Tin tức: mỗi item có id, title, published_at (ISO, giờ VN), url (có thể None), source."""

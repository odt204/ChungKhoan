"""Smoke test nguồn VCI qua vnstock: gọi thật từng hàm cho 1 mã và in kết quả.

Chạy: python scripts/smoke_vci.py [SYMBOL]
Exit code != 0 nếu bất kỳ lời gọi nào lỗi hoặc trả về rỗng.
"""

import os
import sys
import traceback
from importlib.metadata import version

os.environ.setdefault("VNSTOCK_TELEMETRY", "0")

import pandas as pd  # noqa: E402
from vnstock import Company, Finance, Quote  # noqa: E402

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 12)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def check(name, fn):
    print(f"\n===== {name} =====")
    try:
        df = fn()
    except Exception:
        traceback.print_exc()
        return False
    if df is None or len(df) == 0:
        print("RỖNG")
        return False
    print(f"type={type(df).__name__} rows={len(df)} cols={list(df.columns)[:15]}")
    print(df.head(3).to_string(max_colwidth=60))
    if len(df) > 3:
        print("...")
        print(df.tail(2).to_string(max_colwidth=60))
    return True


def main():
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "FPT").upper()
    print(f"vnstock={version('vnstock')} python={sys.version.split()[0]} symbol={symbol}")

    results = {
        "ohlcv_recent": check(
            "Quote.history 1D (2026-01-01 -> nay)",
            lambda: Quote(source="VCI", symbol=symbol).history(start="2026-01-01", interval="1D"),
        ),
        "ohlcv_2020": check(
            "Quote.history 1D (2020-01-01 -> 2020-01-31)",
            lambda: Quote(source="VCI", symbol=symbol).history(
                start="2020-01-01", end="2020-01-31", interval="1D"
            ),
        ),
        "overview": check("Company.overview", lambda: Company(source="VCI", symbol=symbol).overview()),
        "ratio_summary": check(
            "Company.ratio_summary", lambda: Company(source="VCI", symbol=symbol).ratio_summary()
        ),
        "ratio": check(
            "Finance.ratio (quarter)",
            lambda: Finance(source="VCI", symbol=symbol).ratio(period="quarter"),
        ),
        "news": check("Company.news", lambda: Company(source="VCI", symbol=symbol).news()),
    }

    print("\n===== TỔNG KẾT =====")
    for k, ok in results.items():
        print(f"{'PASS' if ok else 'FAIL'}  {k}")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()

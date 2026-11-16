"""Smoke test nguồn VCI: gọi thật adapter (giá, thông tin cơ bản, tin tức) cho 1 mã và in kết quả.

Chạy: python scripts/smoke_vci.py [SYMBOL]
Exit code != 0 nếu bất kỳ lời gọi nào lỗi hoặc trả về rỗng.
"""

import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vnsignal.config import now_vn  # noqa: E402
from vnsignal.data.vci import VCISource  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def check(name, fn, show):
    print(f"\n===== {name} =====")
    try:
        result = fn()
    except Exception:
        traceback.print_exc()
        return False
    if result is None or len(result) == 0:
        print("RỖNG")
        return False
    show(result)
    return True


def main():
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "FPT").upper()
    src = VCISource()
    today = now_vn().date()
    print(f"symbol={symbol} today(VN)={today}")

    results = {
        "ohlcv_recent": check(
            "OHLCV 20 ngày gần nhất", lambda: src.get_ohlcv(symbol, today - timedelta(days=20), today),
            lambda df: print(f"rows={len(df)}\n{df.tail(3).to_string(index=False)}"),
        ),
        "ohlcv_2020": check(
            "OHLCV 01/2020", lambda: src.get_ohlcv(symbol, date(2020, 1, 1), date(2020, 1, 31)),
            lambda df: print(f"rows={len(df)} {df['date'].min()} → {df['date'].max()}"),
        ),
        "fundamentals": check(
            "Thông tin cơ bản + chỉ số TTM", lambda: src.get_fundamentals(symbol),
            lambda f: print(f"{f['overview']['organ_name']} | {len(f['ratios_ttm'])} quý, mới nhất "
                            f"Q{f['ratios_ttm'][-1]['quarter']}/{f['ratios_ttm'][-1]['year']}"),
        ),
        "news": check(
            "Tin tức", lambda: src.get_news(symbol),
            lambda n: print(f"{len(n)} tin, mới nhất: {n[0]['published_at']} {n[0]['title'][:70]}"),
        ),
    }
    print("\n===== TỔNG KẾT =====")
    for k, ok in results.items():
        print(f"{'PASS' if ok else 'FAIL'}  {k}")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()

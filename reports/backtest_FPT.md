# Backtest FPT

_Sinh lúc 2026-10-30 10:10 (giờ VN) bằng `python -m vnsignal.cli backtest`. Số liệu là output thật của code._

## Giả định

- Dữ liệu: OHLCV daily nguồn VCI, giá **đã điều chỉnh** cổ tức/chia tách; sàn HOSE, biên độ ±7%.
- Tín hiệu tính ở giá đóng cửa phiên t, khớp giá mở cửa phiên t+1. Mua bị huỷ nếu phiên khóa trần/không có giao dịch; bán bị hoãn nếu khóa sàn/không có giao dịch.
- T+2: mua ngày T chỉ bán từ phiên chiều T+2 (khớp ATC ở phiên đó).
- Phí mua 0.15%, phí bán 0.15% + thuế bán 0.1%; lô 100.
- Stop-loss = entry − 2×ATR14, take-profit = entry + 3×ATR14; chạm cả hai cùng phiên → tính SL.
- Mỗi lệnh tối đa 35% vốn, rủi ro tối đa 2% vốn. Phần vốn còn lại để tiền mặt (không lãi). Buy-and-hold dùng 100% vốn → so sánh lợi nhuận không cùng mức phơi nhiễm; xem thêm cột thời gian nắm giữ và max drawdown.
- Vốn đọc từ `CAPITAL_VND` chỉ để làm tròn lô; report không hiển thị số tiền.

## Walk-forward

Tối ưu trên in-sample 2020-01-01 → 2023-12-31 (lưới trọng số [0, 0.5, 1, 2], ngưỡng [0.3, 0.4, 0.5], 525 tổ hợp, hàm mục tiêu CAGR / max(max drawdown, 5%), tối thiểu 5 lệnh), kiểm tra out-of-sample từ 2024-01-01.

Trọng số tối ưu: `trend=1, momentum=2, volume=0.5, support_resistance=0.5`, ngưỡng mua/bán ±0.3.

| Chiến lược | Kỳ | Số lệnh | Win rate | Profit factor | Tổng lợi nhuận | CAGR | Max drawdown | Thời gian nắm giữ |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Tối ưu — in-sample | 2020-10-20 → 2023-12-29 | 33 | 63.6% | 2.34 | 24.3% | 7.1% | -5.3% | 59.2% |
| Buy-and-hold — in-sample | 2020-10-20 → 2023-12-29 | 1 | 100.0% | ∞ | 203.0% | 41.6% | -30.6% | 100.0% |
| Tối ưu — **out-of-sample** | 2024-01-02 → 2026-10-29 | 26 | 38.5% | 1.01 | 0.2% | 0.1% | -6.9% | 27.5% |
| Buy-and-hold — **out-of-sample** | 2024-01-02 → 2026-10-29 | 1 | 0.0% | 0.00 | -15.6% | -5.8% | -52.1% | 100.0% |

**Out-of-sample:** CAGR 0.1% vs buy-and-hold -5.8% → **THẮNG buy-and-hold** về lợi nhuận; max drawdown -6.9% (thấp hơn mức -52.1% của buy-and-hold).

## Trọng số trong config.yaml (đang dùng cho tín hiệu live)

Trọng số: `trend=1, momentum=1, volume=0.5, support_resistance=1`, ngưỡng mua 0.4 / bán −0.4.

| Chiến lược | Kỳ | Số lệnh | Win rate | Profit factor | Tổng lợi nhuận | CAGR | Max drawdown | Thời gian nắm giữ |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Config — toàn kỳ | 2020-10-20 → 2026-10-29 | 51 | 52.9% | 1.30 | 11.6% | 1.8% | -11.3% | 42.5% |
| Buy-and-hold — toàn kỳ | 2020-10-20 → 2026-10-29 | 1 | 100.0% | ∞ | 153.4% | 16.7% | -55.4% | 100.0% |
| Config — out-of-sample | 2024-01-02 → 2026-10-29 | 23 | 34.8% | 0.75 | -3.8% | -1.4% | -8.9% | 27.1% |
| Buy-and-hold — out-of-sample | 2024-01-02 → 2026-10-29 | 1 | 0.0% | 0.00 | -15.6% | -5.8% | -52.1% | 100.0% |

**Toàn kỳ:** CAGR 1.8% vs buy-and-hold 16.7% → **THUA buy-and-hold** về lợi nhuận; max drawdown -11.3% (thấp hơn mức -55.4% của buy-and-hold).

**Out-of-sample:** CAGR -1.4% vs buy-and-hold -5.8% → **THẮNG buy-and-hold** về lợi nhuận; max drawdown -8.9% (thấp hơn mức -52.1% của buy-and-hold).

## Danh sách lệnh out-of-sample (trọng số tối ưu)

| Mua | Bán | Giá mua | Giá bán | Lợi nhuận (sau phí, thuế) | Lý do thoát |
|---|---|---:|---:|---:|---|
| 2024-01-08 | 2024-01-12 | 63,920 | 61,952 | -3.5% | SL |
| 2024-02-02 | 2024-02-06 | 65,760 | 68,320 | 3.5% | TP |
| 2024-02-23 | 2024-03-01 | 69,240 | 72,401 | 4.1% | TP |
| 2024-03-07 | 2024-03-13 | 71,600 | 75,358 | 4.8% | TP |
| 2024-03-14 | 2024-03-18 | 77,770 | 74,160 | -5.0% | SL |
| 2024-04-25 | 2024-05-07 | 80,390 | 85,628 | 6.1% | TP |
| 2024-05-14 | 2024-05-22 | 85,320 | 91,468 | 6.8% | TP |
| 2024-06-12 | 2024-07-05 | 97,200 | 103,809 | 6.4% | TP |
| 2024-07-09 | 2024-07-12 | 105,710 | 100,460 | -5.3% | SL |
| 2024-08-13 | 2024-10-10 | 98,560 | 106,322 | 7.4% | TP |
| 2024-10-11 | 2024-10-15 | 107,910 | 104,110 | -3.9% | SL |
| 2024-10-16 | 2024-10-23 | 103,650 | 100,990 | -3.0% | SELL |
| 2024-11-12 | 2024-11-15 | 105,330 | 102,306 | -3.3% | SL |
| 2024-11-28 | 2024-12-04 | 105,930 | 111,797 | 5.1% | TP |
| 2024-12-05 | 2024-12-31 | 110,190 | 117,115 | 5.9% | TP |
| 2025-01-24 | 2025-02-04 | 117,920 | 111,870 | -5.5% | SELL |
| 2025-05-15 | 2025-05-19 | 96,800 | 90,450 | -6.9% | SL |
| 2025-06-17 | 2025-06-24 | 91,840 | 89,760 | -2.7% | SELL |
| 2025-07-07 | 2025-07-30 | 95,160 | 94,960 | -0.6% | SELL |
| 2025-10-29 | 2025-11-12 | 90,880 | 85,640 | -6.1% | SELL |
| 2026-01-08 | 2026-01-16 | 87,970 | 93,544 | 5.9% | TP |
| 2026-01-19 | 2026-01-21 | 97,480 | 94,160 | -3.8% | SL |
| 2026-01-22 | 2026-01-26 | 94,610 | 88,330 | -7.0% | SL |
| 2026-01-28 | 2026-02-06 | 91,830 | 87,880 | -4.7% | SELL |
| 2026-08-04 | 2026-08-14 | 65,820 | 62,015 | -6.2% | SL |
| 2026-09-03 | 2026-09-21 | 66,360 | 66,500 | -0.2% | SELL |

_Đây là kết quả kiểm định quá khứ, không đảm bảo cho tương lai. Không phải khuyến nghị đầu tư._

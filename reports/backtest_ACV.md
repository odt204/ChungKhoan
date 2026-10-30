# Backtest ACV

_Sinh lúc 2026-10-30 10:56 (giờ VN) bằng `python -m vnsignal.cli backtest`. Số liệu là output thật của code._

## Giả định

- Dữ liệu: OHLCV daily nguồn VCI, giá **đã điều chỉnh** cổ tức/chia tách; sàn UPCOM, biên độ ±15%.
- Tín hiệu tính ở giá đóng cửa phiên t, khớp giá mở cửa phiên t+1. Mua bị huỷ nếu phiên khóa trần/không có giao dịch; bán bị hoãn nếu khóa sàn/không có giao dịch.
- T+2: mua ngày T chỉ bán từ phiên chiều T+2 (khớp ATC ở phiên đó).
- Phí mua 0.15%, phí bán 0.15% + thuế bán 0.1%; lô 100.
- Stop-loss = entry − 2×ATR14, take-profit = entry + 3×ATR14; chạm cả hai cùng phiên → tính SL.
- Mỗi lệnh tối đa 35% vốn, rủi ro tối đa 2% vốn. Phần vốn còn lại để tiền mặt (không lãi). Buy-and-hold dùng 100% vốn → so sánh lợi nhuận không cùng mức phơi nhiễm; xem thêm cột thời gian nắm giữ và max drawdown.
- Vốn đọc từ `CAPITAL_VND` chỉ để làm tròn lô; report không hiển thị số tiền.

## Walk-forward

Tối ưu trên in-sample 2020-01-01 → 2023-12-31 (lưới trọng số [0, 0.5, 1, 2], ngưỡng [0.3, 0.4, 0.5], 525 tổ hợp, hàm mục tiêu CAGR / max(max drawdown, 5%), tối thiểu 5 lệnh), kiểm tra out-of-sample từ 2024-01-01.

Trọng số tối ưu: `trend=0, momentum=1, volume=1, support_resistance=0.5`, ngưỡng mua/bán ±0.4.

| Chiến lược | Kỳ | Số lệnh | Win rate | Profit factor | Tổng lợi nhuận | CAGR | Max drawdown | Thời gian nắm giữ |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Tối ưu — in-sample | 2020-10-20 → 2023-12-29 | 24 | 50.0% | 1.87 | 10.7% | 3.2% | -3.8% | 35.8% |
| Buy-and-hold — in-sample | 2020-10-20 → 2023-12-29 | 1 | 100.0% | ∞ | 5.1% | 1.6% | -36.3% | 100.0% |
| Tối ưu — **out-of-sample** | 2024-01-02 → 2026-10-29 | 23 | 56.5% | 1.44 | 7.4% | 2.6% | -5.9% | 36.8% |
| Buy-and-hold — **out-of-sample** | 2024-01-02 → 2026-10-29 | 1 | 100.0% | ∞ | 5.4% | 1.9% | -51.5% | 100.0% |

**Out-of-sample:** CAGR 2.6% vs buy-and-hold 1.9% → **THẮNG buy-and-hold** về lợi nhuận; max drawdown -5.9% (thấp hơn mức -51.5% của buy-and-hold).

## Trọng số trong config.yaml (đang dùng cho tín hiệu live)

Trọng số: `trend=1, momentum=1, volume=0.5, support_resistance=1`, ngưỡng mua 0.4 / bán −0.4.

| Chiến lược | Kỳ | Số lệnh | Win rate | Profit factor | Tổng lợi nhuận | CAGR | Max drawdown | Thời gian nắm giữ |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Config — toàn kỳ | 2020-10-20 → 2026-10-29 | 36 | 47.2% | 1.17 | 4.5% | 0.7% | -6.3% | 34.5% |
| Buy-and-hold — toàn kỳ | 2020-10-20 → 2026-10-29 | 1 | 100.0% | ∞ | 7.4% | 1.2% | -53.1% | 100.0% |
| Config — out-of-sample | 2024-01-02 → 2026-10-29 | 19 | 47.4% | 1.30 | 4.2% | 1.5% | -6.3% | 25.1% |
| Buy-and-hold — out-of-sample | 2024-01-02 → 2026-10-29 | 1 | 100.0% | ∞ | 5.4% | 1.9% | -51.5% | 100.0% |

**Toàn kỳ:** CAGR 0.7% vs buy-and-hold 1.2% → **THUA buy-and-hold** về lợi nhuận; max drawdown -6.3% (thấp hơn mức -53.1% của buy-and-hold).

**Out-of-sample:** CAGR 1.5% vs buy-and-hold 1.9% → **THUA buy-and-hold** về lợi nhuận; max drawdown -6.3% (thấp hơn mức -51.5% của buy-and-hold).

## Danh sách lệnh out-of-sample (trọng số tối ưu)

| Mua | Bán | Giá mua | Giá bán | Lợi nhuận (sau phí, thuế) | Lý do thoát |
|---|---|---:|---:|---:|---|
| 2024-01-26 | 2024-01-30 | 41,620 | 43,870 | 5.0% | TP |
| 2024-01-31 | 2024-02-02 | 43,690 | 47,270 | 7.8% | TP |
| 2024-02-06 | 2024-02-29 | 49,150 | 50,190 | 1.7% | SELL |
| 2024-05-03 | 2024-05-09 | 54,990 | 60,363 | 9.3% | TP |
| 2024-05-20 | 2024-06-03 | 60,700 | 66,978 | 9.9% | TP |
| 2024-09-23 | 2024-09-30 | 65,620 | 63,860 | -3.1% | SELL |
| 2024-10-10 | 2024-10-15 | 66,230 | 70,172 | 5.5% | TP |
| 2024-10-16 | 2024-11-11 | 69,630 | 74,578 | 6.7% | TP |
| 2024-11-12 | 2024-11-15 | 74,130 | 70,087 | -5.8% | SL |
| 2024-11-29 | 2024-12-13 | 75,520 | 72,610 | -4.2% | SELL |
| 2024-12-24 | 2025-01-10 | 76,560 | 72,820 | -5.3% | SL |
| 2025-04-08 | 2025-04-10 | 52,560 | 58,690 | 11.2% | SELL |
| 2025-04-23 | 2025-06-09 | 56,450 | 56,810 | 0.2% | SELL |
| 2025-07-24 | 2025-07-29 | 58,690 | 62,164 | 5.5% | TP |
| 2025-08-07 | 2025-08-22 | 65,000 | 61,476 | -5.8% | SL |
| 2025-10-29 | 2025-11-26 | 54,900 | 52,900 | -4.0% | SELL |
| 2025-12-04 | 2025-12-11 | 54,900 | 59,147 | 7.3% | TP |
| 2025-12-12 | 2025-12-19 | 55,000 | 51,400 | -6.9% | SL |
| 2026-01-09 | 2026-01-14 | 52,900 | 58,035 | 9.3% | TP |
| 2026-01-15 | 2026-01-23 | 61,700 | 56,823 | -8.3% | SL |
| 2026-05-19 | 2026-07-07 | 45,200 | 42,963 | -5.3% | SL |
| 2026-08-04 | 2026-10-22 | 40,000 | 42,862 | 6.7% | TP |
| 2026-10-23 | 2026-10-28 | 43,000 | 40,946 | -5.2% | SL |

_Đây là kết quả kiểm định quá khứ, không đảm bảo cho tương lai. Không phải khuyến nghị đầu tư._

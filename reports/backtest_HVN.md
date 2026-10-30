# Backtest HVN

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

Trọng số tối ưu: `trend=0.5, momentum=2, volume=0, support_resistance=1`, ngưỡng mua/bán ±0.5.

| Chiến lược | Kỳ | Số lệnh | Win rate | Profit factor | Tổng lợi nhuận | CAGR | Max drawdown | Thời gian nắm giữ |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Tối ưu — in-sample | 2020-10-20 → 2023-12-29 | 9 | 44.4% | 1.41 | 3.6% | 1.1% | -4.5% | 5.1% |
| Buy-and-hold — in-sample | 2020-10-20 → 2023-12-29 | 1 | 0.0% | 0.00 | -39.7% | -14.6% | -68.6% | 100.0% |
| Tối ưu — **out-of-sample** | 2024-01-02 → 2026-10-29 | 7 | 42.9% | 0.95 | -0.4% | -0.2% | -4.0% | 6.4% |
| Buy-and-hold — **out-of-sample** | 2024-01-02 → 2026-10-29 | 1 | 100.0% | ∞ | 116.1% | 31.4% | -49.4% | 100.0% |

**Out-of-sample:** CAGR -0.2% vs buy-and-hold 31.4% → **THUA buy-and-hold** về lợi nhuận; max drawdown -4.0% (thấp hơn mức -49.4% của buy-and-hold).

## Trọng số trong config.yaml (đang dùng cho tín hiệu live)

Trọng số: `trend=1, momentum=1, volume=0.5, support_resistance=1`, ngưỡng mua 0.4 / bán −0.4.

| Chiến lược | Kỳ | Số lệnh | Win rate | Profit factor | Tổng lợi nhuận | CAGR | Max drawdown | Thời gian nắm giữ |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Config — toàn kỳ | 2020-10-20 → 2026-10-29 | 50 | 40.0% | 0.85 | -8.4% | -1.4% | -20.9% | 23.4% |
| Buy-and-hold — toàn kỳ | 2020-10-20 → 2026-10-29 | 1 | 100.0% | ∞ | 28.9% | 4.3% | -68.6% | 100.0% |
| Config — out-of-sample | 2024-01-02 → 2026-10-29 | 26 | 50.0% | 1.30 | 9.0% | 3.1% | -11.8% | 29.2% |
| Buy-and-hold — out-of-sample | 2024-01-02 → 2026-10-29 | 1 | 100.0% | ∞ | 116.1% | 31.4% | -49.4% | 100.0% |

**Toàn kỳ:** CAGR -1.4% vs buy-and-hold 4.3% → **THUA buy-and-hold** về lợi nhuận; max drawdown -20.9% (thấp hơn mức -68.6% của buy-and-hold).

**Out-of-sample:** CAGR 3.1% vs buy-and-hold 31.4% → **THUA buy-and-hold** về lợi nhuận; max drawdown -11.8% (thấp hơn mức -49.4% của buy-and-hold).

## Danh sách lệnh out-of-sample (trọng số tối ưu)

| Mua | Bán | Giá mua | Giá bán | Lợi nhuận (sau phí, thuế) | Lý do thoát |
|---|---|---:|---:|---:|---|
| 2024-10-30 | 2024-11-08 | 17,340 | 18,689 | 7.3% | TP |
| 2025-02-17 | 2025-02-19 | 23,640 | 22,820 | -3.9% | SL |
| 2025-03-25 | 2025-03-31 | 23,600 | 22,164 | -6.5% | SL |
| 2025-04-15 | 2025-05-21 | 24,670 | 28,059 | 13.3% | TP |
| 2025-07-22 | 2025-07-29 | 33,700 | 32,368 | -4.3% | SL |
| 2025-09-15 | 2025-09-17 | 35,000 | 37,450 | 6.6% | TP |
| 2026-01-15 | 2026-01-19 | 31,400 | 28,300 | -10.2% | SL |

_Đây là kết quả kiểm định quá khứ, không đảm bảo cho tương lai. Không phải khuyến nghị đầu tư._

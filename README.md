# VNSignal

Hệ thống phân tích & cảnh báo tín hiệu MUA / BÁN / GIỮ cho **FPT, ACV, HVN**, chạy mỗi ngày sau phiên
bằng GitHub Actions. Đây là **công cụ hỗ trợ quyết định, không phải trading bot** — không có chức năng đặt lệnh.

> Đây là tín hiệu tham khảo, không phải khuyến nghị đầu tư.

## Cài đặt local (Windows 11, PowerShell)

Yêu cầu Python **3.11** (production chạy 3.11; `vnstock_ezchart` chưa hỗ trợ 3.14). Nếu Python cài từ
python.org bằng Python install manager:

```powershell
py install 3.11
py -V:3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env   # rồi mở .env điền giá trị
```

`vnstock` và `vnai` không còn trên PyPI, tác giả phát hành qua `https://vnstocks.com/api/simple`
(đã khai báo trong `requirements.txt`). Giấy phép vnstock: dùng cá nhân. Telemetry tuỳ chọn của `vnai`
được tắt bằng `VNSTOCK_TELEMETRY=0`.

## Lệnh

Mọi lệnh chạy qua một entry point:

```powershell
.\.venv\Scripts\python.exe -m vnsignal.cli <command>
```

| Lệnh | Việc làm |
|---|---|
| `backfill [--force]` | Nạp OHLCV daily từ 2020-01-01 cho mã chưa có dữ liệu (`--force`: tải lại, upsert) |
| `eod` | Lấy nến mới nhất; bỏ qua nếu đã có; nến hôm nay chỉ ghi khi đã đóng phiên |
| `fundamentals` | Cập nhật `data/fundamentals/{symbol}.json` |
| `signals` | Tính tín hiệu BUY/SELL/HOLD cho toàn bộ lịch sử, ghi `data/signals/{symbol}.csv` |
| `backtest` | Walk-forward (tối ưu 2020–2023, kiểm tra 2024–nay), ghi `reports/backtest_{symbol}.md` |
| `news` | Tin VCI + RSS CafeF/Vietstock lọc theo mã, dedupe, chấm sentiment, ghi `data/news/{symbol}.jsonl` |

Test: `.\.venv\Scripts\python.exe -m pytest -q`

Kiểm tra nguồn VCI: `.\.venv\Scripts\python.exe scripts\smoke_vci.py FPT`

## Dữ liệu

| File | Nội dung |
|---|---|
| `data/ohlcv/{symbol}.csv` | `date,open,high,low,close,volume` — giá VND **đã điều chỉnh** cổ tức/chia tách |
| `data/fundamentals/{symbol}.json` | Tổng quan công ty + chỉ số TTM 8 quý gần nhất |
| `data/signals/{symbol}.csv` | Tín hiệu từng phiên: điểm, BUY/SELL/HOLD, độ tin cậy, SL/TP, tỷ trọng vốn (%), 3 lý do |

## Tín hiệu

Điểm tổng hợp = trung bình có trọng số (trong `config.yaml`) của 4 rule, mỗi rule cho điểm −1..+1:

- **trend**: giá so với EMA20/EMA50/EMA200, EMA20 so với EMA50 (có ghi chú khi vừa cắt nhau).
- **momentum**: RSI14 < 30 (+1) / > 70 (−1); MACD(12,26,9) vừa cắt lên (+1) / xuống (−1), nếu không thì ±0.5 theo histogram.
- **volume**: volume ≥ 1.5× MA20 xác nhận hướng phiên (+1 phiên tăng / −1 phiên giảm).
- **support_resistance**: vượt đỉnh 20 phiên (+1) / thủng đáy 20 phiên (−1).

Điểm ≥ `buy_threshold` → BUY, ≤ −`sell_threshold` → SELL, còn lại HOLD. Độ tin cậy = |điểm| × 100.
Stop-loss = giá − 2×ATR14, take-profit = giá + 3×ATR14. Tỷ trọng vốn cho lệnh mua = min(35%, 2% × giá / (giá − SL));
số cổ phiếu (làm tròn lô 100) chỉ tính lúc gửi alert bằng `CAPITAL_VND`, không ghi vào file commit.

## Tin tức & sentiment

- Nguồn: tin doanh nghiệp từ VCI (không có URL, dedupe theo `news_id`) + RSS CafeF/Vietstock trong `config.yaml`,
  lọc theo `news_match` / `news_exclude` của từng mã (ví dụ bỏ "FPT Retail" — mã FRT).
- Dedupe theo hash URL (http/https coi như một); tin đã lưu không bị ghi đè.
- Chấm điểm −1..+1 bằng Claude (`news.sentiment_model`, mặc định `claude-haiku-4-5`) qua SDK `anthropic`,
  key lấy từ `ANTHROPIC_API_KEY`. Thiếu key / API lỗi → log warning, tin để chưa chấm, sentiment = 0, lệnh vẫn chạy;
  lần chạy sau có key sẽ chấm bù.
- Sentiment chỉ là **modifier**: trung bình điểm tin trong `window_days` ngày gần nhất × 10 cộng vào confidence
  theo hướng tín hiệu (BUY: tin tốt tăng; SELL: tin xấu tăng; HOLD: không đổi). Không bao giờ đổi BUY/SELL/HOLD.

Ghi chú về dữ liệu VCI:

- VCI trả giá theo nghìn đồng; hệ thống đổi sang VND.
- Khi có cổ tức/chia tách, VCI điều chỉnh lại toàn bộ giá quá khứ. `eod` tải chồng 14 ngày; nếu giá cũ lệch
  quá `adjustment_tolerance` thì tự tải lại toàn bộ lịch sử.
- ACV có 6 phiên 22–29/07/2021 volume = 0 (không có giao dịch) — giữ nguyên như nguồn trả về.

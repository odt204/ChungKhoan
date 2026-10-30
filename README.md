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

Test: `.\.venv\Scripts\python.exe -m pytest -q`

Kiểm tra nguồn VCI: `.\.venv\Scripts\python.exe scripts\smoke_vci.py FPT`

## Dữ liệu

| File | Nội dung |
|---|---|
| `data/ohlcv/{symbol}.csv` | `date,open,high,low,close,volume` — giá VND **đã điều chỉnh** cổ tức/chia tách |
| `data/fundamentals/{symbol}.json` | Tổng quan công ty + chỉ số TTM 8 quý gần nhất |

Ghi chú về dữ liệu VCI:

- VCI trả giá theo nghìn đồng; hệ thống đổi sang VND.
- Khi có cổ tức/chia tách, VCI điều chỉnh lại toàn bộ giá quá khứ. `eod` tải chồng 14 ngày; nếu giá cũ lệch
  quá `adjustment_tolerance` thì tự tải lại toàn bộ lịch sử.
- ACV có 6 phiên 22–29/07/2021 volume = 0 (không có giao dịch) — giữ nguyên như nguồn trả về.

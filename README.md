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
| `alert [--summary]` | Telegram: chỉ gửi mã đổi tín hiệu so với `data/alert_state.json`; `--summary` gửi 1 tin tổng hợp mọi mã |
| `build-site` | Sinh dashboard tĩnh vào `site/` (mở `site/index.html` bằng trình duyệt là xem được) |
| `run-daily [--backfill]` | Cả chuỗi: backfill (nếu thiếu) → eod → fundamentals → signals → news → alert → build-site |

`run-daily`: eod / signals / build-site lỗi thì dừng (exit 1); fundamentals / news / alert lỗi thì log và chạy tiếp.
Có nến mới → gửi Telegram bản tổng hợp (`alert --summary`); ngày nghỉ (không có nến mới) → chỉ gửi khi tín hiệu đổi.

Test: `.\.venv\Scripts\python.exe -m pytest -q`

Kiểm tra nguồn VCI: `.\.venv\Scripts\python.exe scripts\smoke_vci.py FPT`

## Dữ liệu

| File | Nội dung |
|---|---|
| `data/ohlcv/{symbol}.csv` | `date,open,high,low,close,volume` — giá VND **đã điều chỉnh** cổ tức/chia tách |
| `data/fundamentals/{symbol}.json` | Tổng quan công ty + chỉ số TTM 8 quý gần nhất |
| `data/signals/{symbol}.csv` | Tín hiệu từng phiên: điểm, BUY/SELL/HOLD, độ tin cậy, SL/TP, tỷ trọng vốn (%), 3 lý do |
| `data/news/{symbol}.jsonl` | Tin tức đã dedupe kèm điểm sentiment |
| `data/alert_state.json` | Tín hiệu đã báo gần nhất của từng mã (để chỉ alert khi đổi) |
| `reports/backtest_{symbol}.md` / `.json` | Kết quả backtest (chỉ %) |

Ghi chú về dữ liệu VCI:

- VCI trả giá theo nghìn đồng; hệ thống đổi sang VND.
- Khi có cổ tức/chia tách, VCI điều chỉnh lại toàn bộ giá quá khứ. `eod` tải chồng 14 ngày; nếu giá cũ lệch
  quá `adjustment_tolerance` thì tự tải lại toàn bộ lịch sử.
- ACV có 6 phiên 22–29/07/2021 volume = 0 (không có giao dịch) — giữ nguyên như nguồn trả về.

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

## Dashboard

`build-site` sinh `site/` (không commit, chỉ deploy qua GitHub Actions):

- `index.html`: 3 thẻ tín hiệu hiện tại; `{symbol}.html`: nến + EMA20/50/200 + volume + mũi tên khi đổi sang MUA/BÁN,
  RSI14, MACD, ATR14 (đồng bộ cuộn/zoom), lịch sử đổi tín hiệu, tin tức kèm điểm sentiment, bảng backtest.
- Dữ liệu chart nằm ở `site/data/{symbol}.json` và được nhúng sẵn vào trang, nên mở trực tiếp bằng `file://`
  vẫn chạy (cần Internet để tải `lightweight-charts@4.2.3` từ jsDelivr).
- Thuần HTML/CSS/JS, giao diện sáng/tối theo hệ điều hành, hiển thị tốt từ 375px. Không hiển thị vốn hay số tiền.

Xem local:

```powershell
.\.venv\Scripts\python.exe -m vnsignal.cli build-site
Start-Process site\index.html
```

## Cảnh báo Telegram

- Gửi qua Bot API `sendMessage` với `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Thiếu env → warning, không gửi, lệnh không lỗi.
- `alert`: so tín hiệu mới nhất với `data/alert_state.json`, chỉ gửi mã đổi trạng thái (mã chưa có trong state
  coi như đổi). State của một mã chỉ cập nhật khi gửi thành công → gửi lỗi sẽ thử lại lần chạy sau.
- `alert --summary`: một tin tổng hợp mọi mã (đánh dấu mã đổi tín hiệu), gửi kể cả khi không đổi.
- Message có giá đóng cửa, SL, TP, khối lượng (số cổ phiếu tính từ `CAPITAL_VND`, làm tròn lô 100, chỉ cho MUA),
  độ tin cậy sau sentiment, 3 lý do; dòng cuối: "Đây là tín hiệu tham khảo, không phải khuyến nghị đầu tư."

## Setup GitHub

Repo phải **public** (GitHub Pages trên gói Free chỉ dùng được cho repo public). Mọi dữ liệu commit lên repo
chỉ gồm giá, tín hiệu, %, tin tức — không có vốn hay secret.

### 1. Tạo repo và push

1. Trên github.com: **New repository** → đặt tên (ví dụ `vnsignal`) → **Public** → *không* tick thêm README/.gitignore.
2. Trên máy (PowerShell, trong thư mục project):

   ```powershell
   git remote add origin https://github.com/<user>/<repo>.git
   git push -u origin main
   ```

### 2. Thêm Secrets

**Settings → Secrets and variables → Actions → New repository secret**, tạo 4 secret (giá trị giống `.env`):

| Secret | Dùng cho |
|---|---|
| `CAPITAL_VND` | Tính số cổ phiếu trong tin Telegram (không hiện trên dashboard) |
| `TELEGRAM_BOT_TOKEN` | Gửi alert |
| `TELEGRAM_CHAT_ID` | Gửi alert |
| `ANTHROPIC_API_KEY` | Chấm sentiment tin tức |

Thiếu secret nào thì bước tương ứng chỉ log warning, pipeline vẫn chạy.

### 3. Bật GitHub Pages

**Settings → Pages → Build and deployment → Source: GitHub Actions.** Không chọn branch — site được deploy
từ artifact của workflow `daily`.

### 4. Chạy thử lần đầu

1. Tab **Actions** → nếu GitHub hỏi, bấm bật workflows cho repo.
2. Chọn **smoke-vci** → **Run workflow** (nhánh `main`). Workflow này chỉ kiểm tra runner GitHub (ở nước ngoài)
   gọi được VCI, CafeF, Vietstock và cài được vnstock. Phải xanh trước khi dùng workflow `daily`.
3. Chọn **daily** → **Run workflow** (để `backfill` tắt, vì data đã có trong repo). Workflow chạy `run-daily`,
   commit thay đổi trong `data/` bằng `github-actions[bot]`, rồi deploy `site/` lên Pages.
4. Dashboard: `https://<user>.github.io/<repo>/` (link cũng hiện ở job **deploy** và Settings → Pages).

Sau đó `daily` tự chạy lúc `cron: "20 8 * * 1-5"` = 08:20 UTC = **15:20 giờ VN, thứ Hai–thứ Sáu**. Ngày lễ VN
không có nến mới: workflow vẫn chạy nhưng không đổi data và không gửi bản tổng hợp.
Chọn `backfill = true` khi chạy tay để tải lại toàn bộ lịch sử từ 2020-01-01 (ví dụ sau khi xoá data).

### Lưu ý về GitHub Actions

- Lịch `cron` của GitHub có thể **trễ 5–30 phút** (đôi khi hơn) vào giờ cao điểm; không chạy đúng từng phút.
- GitHub **tự tắt scheduled workflow nếu repo không có commit nào trong 60 ngày**. Workflow `daily` tự commit
  data mỗi ngày giao dịch nên thường không bị; nếu bị tắt, vào tab Actions bật lại.
- Pages trên gói Free chỉ cho repo public.

/* Vẽ biểu đồ giá + RSI/MACD/ATR bằng lightweight-charts 4.2.3 từ dữ liệu nhúng trong trang
   (<script id="chart-data">) — chạy được cả khi mở bằng file://. */
(function () {
  "use strict";

  var data = JSON.parse(document.getElementById("chart-data").textContent);
  if (typeof LightweightCharts === "undefined") {
    document.getElementById("chart-error").hidden = false;
    return;
  }

  var css = getComputedStyle(document.documentElement);
  var color = function (name) { return css.getPropertyValue(name).trim(); };
  var fmt = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
  var narrow = window.matchMedia("(max-width: 760px)").matches;

  // Giữ đủ mọi phiên (giai đoạn warm-up là điểm trắng {time}) để chỉ số logic giữa các
  // chart trùng nhau — đồng bộ cuộn/zoom theo logical range mới thẳng hàng.
  function series(key) {
    return data.t.map(function (t, i) {
      return data[key][i] === null ? { time: t } : { time: t, value: data[key][i] };
    });
  }

  function makeChart(id, opts) {
    var chart = LightweightCharts.createChart(document.getElementById(id), Object.assign({
      autoSize: true,
      layout: { background: { type: "solid", color: color("--surface") }, textColor: color("--muted"), fontSize: 11 },
      grid: { vertLines: { color: color("--grid") }, horzLines: { color: color("--grid") } },
      // cùng độ rộng trục giá ở mọi chart để trục thời gian thẳng hàng
      rightPriceScale: { borderColor: color("--border"), minimumWidth: 76 },
      timeScale: { borderColor: color("--border") },
      localization: { locale: "vi-VN", priceFormatter: function (p) { return fmt.format(p); } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      handleScroll: { vertTouchDrag: false },
    }, opts || {}));
    return chart;
  }

  var buy = color("--buy"), sell = color("--sell");

  // Giá: nến + EMA + volume + marker đổi tín hiệu
  var price = makeChart("chart-price");
  var candles = price.addCandlestickSeries({
    upColor: buy, downColor: sell, borderUpColor: buy, borderDownColor: sell, wickUpColor: buy, wickDownColor: sell,
  });
  var ohlc = [];
  for (var i = 0; i < data.t.length; i++) {
    ohlc.push({ time: data.t[i], open: data.o[i], high: data.h[i], low: data.l[i], close: data.c[i] });
  }
  candles.setData(ohlc);
  candles.priceScale().applyOptions({ scaleMargins: { top: 0.05, bottom: 0.22 } });
  [["ema_fast", "--ema-fast"], ["ema_mid", "--ema-mid"], ["ema_slow", "--ema-slow"]].forEach(function (e) {
    price.addLineSeries({ color: color(e[1]), lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      crosshairMarkerVisible: false }).setData(series(e[0]));
  });
  var volume = price.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false,
    priceLineVisible: false });
  price.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
  volume.setData(data.t.map(function (t, i) {
    return { time: t, value: data.v[i], color: (data.c[i] >= data.o[i] ? buy : sell) + "55" };
  }));
  candles.setMarkers(data.markers.map(function (m) {
    return m.s === "BUY"
      ? { time: m.t, position: "belowBar", color: buy, shape: "arrowUp", text: narrow ? "" : "MUA" }
      : { time: m.t, position: "aboveBar", color: sell, shape: "arrowDown", text: narrow ? "" : "BÁN" };
  }));

  // RSI
  var rsi = makeChart("chart-rsi");
  var rsiLine = rsi.addLineSeries({ color: color("--accent"), lineWidth: 1, priceLineVisible: false });
  rsiLine.setData(series("rsi"));
  data.rsi_levels.forEach(function (lv) {
    rsiLine.createPriceLine({ price: lv, color: color("--muted"), lineWidth: 1, lineStyle: 2, axisLabelVisible: true });
  });

  // MACD
  var macd = makeChart("chart-macd");
  macd.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false }).setData(
    series("macd_hist").map(function (p) {
      return p.value === undefined ? p : { time: p.time, value: p.value, color: (p.value >= 0 ? buy : sell) + "88" };
    })
  );
  macd.addLineSeries({ color: color("--ema-mid"), lineWidth: 1, priceLineVisible: false }).setData(series("macd"));
  macd.addLineSeries({ color: color("--ema-fast"), lineWidth: 1, priceLineVisible: false }).setData(series("macd_signal"));

  // ATR
  var atr = makeChart("chart-atr");
  atr.addLineSeries({ color: color("--ema-slow"), lineWidth: 1, priceLineVisible: false }).setData(series("atr"));

  // Đồng bộ trục thời gian giữa các chart
  var charts = [price, rsi, macd, atr], syncing = false;
  charts.forEach(function (src) {
    src.timeScale().subscribeVisibleLogicalRangeChange(function (range) {
      if (syncing || !range) return;
      syncing = true;
      charts.forEach(function (dst) { if (dst !== src) dst.timeScale().setVisibleLogicalRange(range); });
      syncing = false;
    });
  });

  // Nút chọn khoảng thời gian
  var n = data.t.length;
  function showBars(bars) {
    if (!bars || bars >= n) { price.timeScale().fitContent(); return; }
    price.timeScale().setVisibleLogicalRange({ from: n - bars, to: n + 2 });
  }
  var buttons = document.querySelectorAll(".range button");
  function select(btn) {
    buttons.forEach(function (b) { b.setAttribute("aria-pressed", String(b === btn)); });
    showBars(parseInt(btn.dataset.bars, 10));
  }
  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () { select(btn); });
  });
  // Màn hình hẹp: mặc định 3 tháng cho dễ đọc; rộng: 1 năm
  select(document.querySelector('.range button[data-bars="' + (narrow ? 66 : 250) + '"]'));
})();

import re

with open('dashboard.html', 'r', encoding='utf-8') as f:
    html = f.read()

if 'lightweight-charts' not in html:
    html = html.replace('<script defer src=\"../Analysis/dashboard/shared.js\"></script>', 
        '<script defer src=\"../Analysis/dashboard/shared.js\"></script>\n  <script src=\"https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js\"></script>')

if 'chart-modal-overlay' not in html:
    modal_css = '''
    /* ── Modal ────────────────────────────────────────────────────────────── */
    .chart-modal-overlay {
      position: fixed; top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0,0,0,0.8); backdrop-filter: blur(4px);
      display: none; justify-content: center; align-items: center; z-index: 9999;
    }
    .chart-modal-overlay.active { display: flex; }
    .chart-modal {
      background: var(--bg-elev-1); border: 1px solid var(--border); border-radius: 8px;
      width: 90vw; height: 85vh; display: flex; flex-direction: column; overflow: hidden;
      box-shadow: 0 20px 40px rgba(0,0,0,0.5);
    }
    .chart-modal-header {
      padding: 12px 20px; border-bottom: 1px solid var(--border);
      display: flex; justify-content: space-between; align-items: center;
    }
    .chart-modal-title { font-family: var(--font-display); font-weight: 600; font-size: 16px; }
    .chart-modal-close {
      background: none; border: none; color: var(--text-muted); cursor: pointer;
      font-size: 24px; line-height: 1; padding: 0;
    }
    .chart-modal-close:hover { color: var(--text-primary); }
    #chart-container { flex: 1; background: #131722; position: relative; }
    .chart-loader {
      position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
      color: var(--accent); font-family: var(--font-data); font-size: 14px;
      display: none;
    }
    '''
    html = html.replace('/* ── Header ───────────────────────────────────────────────────────────── */', modal_css + '\n    /* ── Header ───────────────────────────────────────────────────────────── */')

if 'id="chart-modal"' not in html:
    modal_html = '''
<!-- Chart Modal -->
<div id="chart-modal" class="chart-modal-overlay">
  <div class="chart-modal">
    <div class="chart-modal-header">
      <div id="chart-modal-title" class="chart-modal-title">Trade Setup</div>
      <button class="chart-modal-close" onclick="closeChartModal()">&times;</button>
    </div>
    <div id="chart-container">
      <div id="chart-loader" class="chart-loader">Loading candles...</div>
    </div>
  </div>
</div>
'''
    html = html.replace('<header class="hdr">', modal_html + '\n<header class="hdr">')

if 'openChartModal' not in html:
    modal_js = '''
// ── Chart Logic ─────────────────────────────────────────────────────────
let chartInstance = null;
let candleSeries = null;

function closeChartModal() {
  document.getElementById('chart-modal').classList.remove('active');
  if (chartInstance) {
    chartInstance.remove();
    chartInstance = null;
    candleSeries = null;
  }
}

async function openChartModal(r) {
  const modal = document.getElementById('chart-modal');
  const title = document.getElementById('chart-modal-title');
  const loader = document.getElementById('chart-loader');
  const container = document.getElementById('chart-container');
  
  modal.classList.add('active');
  title.innerHTML = ${r.instrument} &middot;  : NY &middot; ;
  loader.style.display = 'block';
  
  if (chartInstance) {
    chartInstance.remove();
    chartInstance = null;
  }

  try {
    const ts_ns = r.entry_ts_ns || r.sig_ts;
    const resp = await fetch(http://localhost:8001/v7_candles?instrument=&ts_ns=&window=90);
    if (!resp.ok) throw new Error("Failed to fetch candles");
    let data = await resp.json();
    
    const chartData = data.map(d => ({
      time: d.time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close
    }));

    loader.style.display = 'none';

    chartInstance = LightweightCharts.createChart(container, {
      layout: { background: { color: '#131722' }, textColor: '#d1d4dc' },
      grid: { vertLines: { color: 'rgba(42, 46, 57, 0)' }, horzLines: { color: 'rgba(42, 46, 57, 0.6)' } },
      timeScale: { timeVisible: true, secondsVisible: false },
    });

    candleSeries = chartInstance.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
      wickUpColor: '#26a69a', wickDownColor: '#ef5350'
    });
    
    candleSeries.setData(chartData);
    
    candleSeries.createPriceLine({ price: r.entry_price, color: '#2962FF', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: 'Entry' });
    if (r.stop_price) candleSeries.createPriceLine({ price: r.stop_price, color: '#ef5350', lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: 'Stop' });
    if (r.target_price) candleSeries.createPriceLine({ price: r.target_price, color: '#26a69a', lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: 'Target' });
    
    if (r.ltf_bot && r.ltf_top) {
      candleSeries.createPriceLine({ price: r.ltf_bot, color: 'rgba(255,255,255,0.4)', lineWidth: 1, lineStyle: 3 });
      candleSeries.createPriceLine({ price: r.ltf_top, color: 'rgba(255,255,255,0.4)', lineWidth: 1, lineStyle: 3 });
    }

    const tradeTime = Math.floor(ts_ns / 1e9);
    chartInstance.timeScale().setVisibleLogicalRange({ from: chartTimeIndex(chartData, tradeTime) - 30, to: chartTimeIndex(chartData, tradeTime) + 60 });

  } catch (err) {
    loader.textContent = "Error: " + err.message;
  }
}

function chartTimeIndex(data, time) {
  let idx = data.findIndex(d => d.time >= time);
  return idx === -1 ? data.length - 1 : idx;
}

window.addEventListener('resize', () => {
  if (chartInstance) {
    const container = document.getElementById('chart-container');
    chartInstance.resize(container.clientWidth, container.clientHeight);
  }
});
</script>'''
    html = html.replace('</script>\n</body>', modal_js + '\n</body>')

html = re.sub(r'return <tr>\s*<td>\$\{r.date\}</td>', 
    'const rowJson = JSON.stringify(r).replace(/\"/g, \\'&quot;\\');\n    return <tr onclick=\"openChartModal()\" style=\"cursor:pointer\" class=\"trade-row\">\n      <td></td>', 
    html)

html = html.replace('CT |', 'NY |')

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Dashboard patched!')

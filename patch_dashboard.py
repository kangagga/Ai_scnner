#!/usr/bin/env python3
"""
patch_dashboard.py — Tambahkan loadPortfolio, loadPerformance, loadMarketRegime,
dan bottom nav click handler ke dashboard.html.
Jalankan dari direktori ~/ai-scanner: python3 patch_dashboard.py
"""

with open('dashboard.html', 'r') as f:
    content = f.read()

old = '''// ── REFRESH LOOP ─────────────────────────────────────────────
async function refresh() {
  await Promise.all([loadStatus(), loadSignals(), loadStats()]);
}

refresh();
setInterval(refresh, 10000);
</script>'''

new = '''// ── LOAD PORTFOLIO (data real: positions, heat, streak) ────────
async function loadPortfolio() {
  try {
    const r = await fetch('/api/portfolio');
    const d = await r.json();
    document.getElementById('openPos').textContent = `${d.open_positions} / ${d.max_positions}`;
    document.getElementById('totalPos').textContent = `Total ${d.total_trades} Trade`;
    document.getElementById('portHeat').textContent = (d.portfolio_heat || 0).toFixed(1) + '%';
    document.getElementById('heatStatus').textContent =
      d.portfolio_heat > 15 ? 'Tinggi' : (d.portfolio_heat > 8 ? 'Normal' : 'Rendah');
    document.getElementById('streakLoss').textContent = d.consecutive_loss || 0;
    const streakEl = document.getElementById('streakLoss').nextElementSibling;
    if (streakEl) {
      streakEl.textContent = d.trading_halted ? `⛔ ${d.halt_reason || 'Halted'}` : `Balance $${(d.balance||0).toFixed(2)}`;
      streakEl.style.color = d.trading_halted ? '#ff4444' : '#00ff88';
    }
  } catch(e) { console.error('loadPortfolio error', e); }
}

// ── LOAD PERFORMANCE (data real: win rate, PnL, equity curve) ──
async function loadPerformance() {
  try {
    const r = await fetch('/api/performance');
    const d = await r.json();
    const pnlSign = d.pnl_pct_7d >= 0 ? '+' : '';
    document.getElementById('totalPnl').textContent = `${pnlSign}${d.pnl_pct_7d || 0}%`;
    document.getElementById('totalPnl').style.color = d.pnl_pct_7d >= 0 ? '#00ff88' : '#ff4444';
    document.getElementById('pnlUsdt').textContent = `${d.total_pnl_usd >= 0 ? '+' : ''}${(d.total_pnl_usd||0).toFixed(2)} USDT`;
    document.getElementById('winRate').textContent = `${d.win_rate || 0}%`;
    document.getElementById('winCount').textContent = `${d.wins || 0} / ${d.total_trades || 0}`;
    document.getElementById('profitFactor').textContent = (d.profit_factor || 0).toFixed(2);

    if (d.equity_curve && d.equity_curve.length >= 2) {
      const balances = d.equity_curve.map(p => p.balance);
      chartData.length = 0;
      balances.forEach(b => chartData.push(b));
      chart.draw(chartData);
    }
  } catch(e) { console.error('loadPerformance error', e); }
}

// ── LOAD MARKET REGIME (data real: BTC trend, fear&greed) ──────
async function loadMarketRegime() {
  try {
    const r = await fetch('/api/market_regime');
    const d = await r.json();
    const isBullish = d.regime === 'BULLISH';
    const isBearish = d.regime === 'BEARISH';
    const icon = isBullish ? '🐂' : (isBearish ? '🐻' : '➡️');
    const color = isBullish ? '#00ff88' : (isBearish ? '#ff4444' : '#ffaa00');
    const tag = document.getElementById('marketRegime');
    tag.textContent = `${icon} ${d.regime}`;
    tag.style.color = color;
    document.getElementById('confPct').textContent = `${d.fear_greed_value}% (${d.fear_greed_label})`;
    document.getElementById('confBar').style.width = `${d.fear_greed_value}%`;
  } catch(e) { console.error('loadMarketRegime error', e); }
}

// ── BOTTOM NAV (sederhana — highlight aktif, info coming soon) ──
document.querySelectorAll('.nav-item').forEach((item, idx) => {
  item.style.cursor = 'pointer';
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    item.classList.add('active');
    const labels = ['Dashboard', 'Scanner', 'Portfolio', 'Log', 'Settings'];
    if (idx !== 0) {
      alert(`Halaman "${labels[idx]}" sedang dalam pengembangan.`);
    }
  });
});

// ── REFRESH LOOP ─────────────────────────────────────────────
async function refresh() {
  await Promise.all([
    loadStatus(), loadSignals(), loadStats(),
    loadPortfolio(), loadPerformance(), loadMarketRegime()
  ]);
}

refresh();
setInterval(refresh, 10000);
</script>'''

if old not in content:
    print("GAGAL: pattern refresh loop tidak ditemukan persis. Tidak ada perubahan dilakukan.")
else:
    content = content.replace(old, new, 1)
    with open('dashboard.html', 'w') as f:
        f.write(content)
    print("OK: fungsi loadPortfolio, loadPerformance, loadMarketRegime, dan nav click ditambahkan")
    print(f"Panjang file baru: {len(content)} karakter")

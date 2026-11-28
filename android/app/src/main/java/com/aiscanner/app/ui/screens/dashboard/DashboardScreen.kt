package com.aiscanner.app.ui.screens.dashboard

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.draw.clip
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.aiscanner.app.data.api.ApiService
import com.aiscanner.app.data.api.DashboardResponse
import com.aiscanner.app.ui.components.ActivityLogItem
import com.aiscanner.app.ui.components.BotStatusPanel
import com.aiscanner.app.ui.components.DisconnectedBanner
import com.aiscanner.app.ui.components.EmptyState
import com.aiscanner.app.ui.components.LoadingIndicator
import com.aiscanner.app.ui.components.MarketAssetCard
import com.aiscanner.app.ui.components.ScannerProgressBar
import com.aiscanner.app.ui.components.ScannerRadar
import com.aiscanner.app.ui.components.SectionTitle
import com.aiscanner.app.ui.components.SignalMonitorRow
import com.aiscanner.app.ui.components.StatCard
import com.aiscanner.app.ui.components.StatusBanner
import com.aiscanner.app.ui.screens.UiState
import com.aiscanner.app.ui.theme.AmberWarn
import com.aiscanner.app.ui.theme.BluePrimary
import com.aiscanner.app.ui.theme.GreenPrimary
import com.aiscanner.app.ui.theme.NavyCard
import com.aiscanner.app.ui.theme.NeonCyan
import com.aiscanner.app.ui.theme.PurplePrimary
import com.aiscanner.app.ui.theme.RedLoss
import com.aiscanner.app.ui.theme.TextPrimary
import com.aiscanner.app.ui.theme.TextSecondary
import com.aiscanner.app.util.formatInt
import com.aiscanner.app.util.formatMoney
import com.aiscanner.app.util.formatPercent
import com.aiscanner.app.util.formatSignedMoney
import com.aiscanner.app.util.formatSignedPercent

@Composable
fun DashboardScreen(viewModel: DashboardViewModel) {
    val state by viewModel.uiState.collectAsState()
    val scanProgress by viewModel.scanProgress.collectAsState()
    val activityLogs by viewModel.activityLogs.collectAsState()
    val signals by viewModel.signals.collectAsState()
    val market by viewModel.marketAnalysis.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        DashboardHeader(onRefresh = { viewModel.load() })

        Spacer(Modifier.height(16.dp))

        when (state) {
            is UiState.Loading -> LoadingIndicator()

            is UiState.Error -> {
                val err = state as UiState.Error
                if (err.disconnected) {
                    DisconnectedBanner()
                    Spacer(Modifier.height(16.dp))
                    EmptyState(
                        title = "Tidak dapat memuat dashboard",
                        subtitle = err.message + "\nPastikan server bot berjalan dan alamat API sudah benar."
                    )
                } else {
                    StatusBanner(text = err.message, color = RedLoss)
                }
            }

            is UiState.Success -> DashboardContent(
                data = (state as UiState.Success).data,
                scanProgress = scanProgress,
                activityLogs = activityLogs,
                signals = signals,
                market = market
            )
        }
    }
}

@Composable
private fun DashboardHeader(onRefresh: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                text = buildAnnotatedString {
                    withStyle(androidx.compose.ui.text.SpanStyle(color = TextPrimary, fontWeight = FontWeight.Bold)) {
                        append("AI ")
                    }
                    withStyle(androidx.compose.ui.text.SpanStyle(color = NeonCyan, fontWeight = FontWeight.Bold)) {
                        append("SCANNER")
                    }
                },
                style = MaterialTheme.typography.headlineSmall
            )
            Text(
                text = "Smart Crypto Trading Assistant",
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary
            )
        }
        IconButton(onClick = onRefresh) {
            Icon(Icons.Filled.Refresh, contentDescription = "Refresh", tint = NeonCyan)
        }
    }
}

@Composable
private fun DashboardContent(
    data: DashboardResponse,
    scanProgress: ApiService.ScanProgress?,
    activityLogs: List<ApiService.LogItem>,
    signals: List<com.aiscanner.app.data.api.Signal>,
    market: com.aiscanner.app.data.api.MarketAnalysis?
) {
    val bot = data.bot
    val portfolio = data.portfolio
    val perf = data.performance
    val sig = data.signals

    val paused = bot?.paused == true
    val running = !paused && (bot?.running != false)

    // ── Bagian 2: Bot Status ──────────────────────────────────────────────
    BotStatusPanel(running = running, paperMode = true)
    Spacer(Modifier.height(16.dp))

    // ── Bagian 3: LIVE CRYPTO SCANNER ─────────────────────────────────────
    LiveCryptoScanner(scanProgress = scanProgress, running = running)
    Spacer(Modifier.height(20.dp))

    // ── Bagian 4: Market Overview ─────────────────────────────────────────
    SectionTitle("Ringkasan Pasar Crypto")
    MarketOverview(market = market)
    Spacer(Modifier.height(20.dp))

    // ── Bagian 5: Signal Monitor ──────────────────────────────────────────
    SectionTitle("Signal Monitor")
    SignalMonitor(signals = signals)
    Spacer(Modifier.height(20.dp))

    // ── Bagian 6: Trading Performance ─────────────────────────────────────
    SectionTitle("Performa Trading (Paper Trading)")
    TradingPerformance(portfolio = portfolio, perf = perf, sig = sig)
    Spacer(Modifier.height(20.dp))

    // ── Bagian 7: Grafik Equity ───────────────────────────────────────────
    SectionTitle("Grafik Equity (7 hari)")
    EquitySection(perf = perf)
    Spacer(Modifier.height(20.dp))

    // ── Bagian 8: Aktivitas Terakhir ──────────────────────────────────────
    SectionTitle("Aktivitas Terakhir")
    ActivityLogSection(logs = activityLogs)
}

@Composable
private fun LiveCryptoScanner(
    scanProgress: ApiService.ScanProgress?,
    running: Boolean
) {
    val current = scanProgress?.current
    val scanning = running && !current.isNullOrBlank()

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(NavyCard)
            .padding(16.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            ScannerRadar(scanning = scanning, size = 110)
            Spacer(Modifier.width(16.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = when {
                        !running -> "Bot Berhenti"
                        scanning -> "Sedang Memindai Market..."
                        else -> "Scanner Standby"
                    },
                    style = MaterialTheme.typography.titleMedium,
                    color = if (scanning) NeonCyan else TextPrimary,
                    fontWeight = FontWeight.Bold
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text = if (scanning) {
                        "Menganalisis peluang terbaik di pasar crypto"
                    } else {
                        "Menunggu perintah pemindaian"
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary
                )
                Spacer(Modifier.height(12.dp))
                ScannerProgressBar(progress = scanProgress?.pct, scanning = scanning)
            }
        }

        if (scanning) {
            Spacer(Modifier.height(14.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                StatCard(
                    label = "Pair Diperiksa",
                    value = formatInt(scanProgress?.done),
                    modifier = Modifier.weight(1f)
                )
                StatCard(
                    label = "Total Target",
                    value = formatInt(scanProgress?.total),
                    modifier = Modifier.weight(1f)
                )
            }
            Spacer(Modifier.height(10.dp))
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("▸", color = NeonCyan)
                Spacer(Modifier.width(8.dp))
                Text(
                    text = "Menganalisis: $current",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextPrimary
                )
            }
        } else {
            Spacer(Modifier.height(12.dp))
            StatusBanner(
                text = if (!running) "Bot dalam keadaan berhenti" else "Tidak ada proses pemindaian aktif",
                color = if (!running) RedLoss else TextSecondary
            )
        }
    }
}

@Composable
private fun MarketOverview(market: com.aiscanner.app.data.api.MarketAnalysis?) {
    val btcPrice = market?.btcPrice
    if (btcPrice == null) {
        EmptyState(
            title = "Data pasar belum tersedia",
            subtitle = "Ringkasan pasar muncul saat backend menyediakan harga aset."
        )
        return
    }
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        MarketAssetCard(
            symbol = "BTC",
            pair = "BTC/USDT",
            price = formatMoney(btcPrice),
            changePct = market?.btcTrend ?: "—",
            changePositive = market?.bullish == true,
            modifier = Modifier.weight(1f)
        )
    }
}

@Composable
private fun SignalMonitor(signals: List<com.aiscanner.app.data.api.Signal>) {
    if (signals.isEmpty()) {
        EmptyState(
            title = "Belum ada sinyal",
            subtitle = "Sinyal baru akan muncul setelah scanner menemukan peluang."
        )
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        signals.take(6).forEach { s ->
            SignalMonitorRow(
                direction = s.signal ?: "WAIT",
                symbol = s.symbol ?: "—",
                timeframe = s.timeframe ?: "—",
                confidence = s.confidence?.let { formatPercent(it) },
                time = s.timestamp ?: ""
            )
        }
    }
}

@Composable
private fun TradingPerformance(
    portfolio: com.aiscanner.app.data.api.Portfolio?,
    perf: com.aiscanner.app.data.api.Performance?,
    sig: com.aiscanner.app.data.api.SignalSummary?
) {
    val equity = perf?.equityCurve?.lastOrNull()?.balance ?: portfolio?.balance ?: 0.0

    // Kartu ringkas utama
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard(
            label = "Total Equity",
            value = formatMoney(equity),
            modifier = Modifier.weight(1f),
            valueColor = GreenPrimary
        )
        StatCard(
            label = "Win Rate",
            value = if (perf?.winRate == null) "N/A" else formatPercent(perf.winRate),
            modifier = Modifier.weight(1f),
            valueColor = PurplePrimary
        )
    }
    Spacer(Modifier.height(12.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard(
            label = "Profit Factor",
            value = perf?.profitFactor?.toString() ?: "N/A",
            modifier = Modifier.weight(1f),
            valueColor = BluePrimary
        )
        StatCard(
            label = "Max Drawdown",
            value = formatPercent(portfolio?.drawdownPct),
            modifier = Modifier.weight(1f),
            valueColor = if ((portfolio?.drawdownPct ?: 0.0) > 10.0) RedLoss else TextPrimary
        )
    }

    Spacer(Modifier.height(16.dp))

    // Statistik lengkap
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard(
            label = "Virtual Balance (PAPER)",
            value = formatMoney(portfolio?.balance),
            modifier = Modifier.weight(1f),
            valueColor = GreenPrimary
        )
        StatCard(
            label = "Equity",
            value = formatMoney(equity),
            modifier = Modifier.weight(1f)
        )
    }
    Spacer(Modifier.height(12.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard(
            label = "PnL Harian",
            value = formatSignedMoney(portfolio?.dailyPnl),
            modifier = Modifier.weight(1f),
            valueColor = if ((portfolio?.dailyPnl ?: 0.0) >= 0) GreenPrimary else RedLoss,
            sub = formatSignedPercent(portfolio?.dailyPnlPct)
        )
        StatCard(
            label = "Realized PnL",
            value = if (perf?.totalPnlUsd == null) "N/A" else formatSignedMoney(perf.totalPnlUsd),
            modifier = Modifier.weight(1f),
            valueColor = if ((perf?.totalPnlUsd ?: 0.0) >= 0) GreenPrimary else RedLoss
        )
    }
    Spacer(Modifier.height(12.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard(
            label = "Total Signals",
            value = formatInt(sig?.total),
            modifier = Modifier.weight(1f)
        )
        StatCard(
            label = "Open Trades",
            value = formatInt(portfolio?.openPositions),
            modifier = Modifier.weight(1f)
        )
    }
    Spacer(Modifier.height(12.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard(
            label = "Closed Trades",
            value = if (perf?.totalTrades == null) "N/A" else formatInt(perf.totalTrades),
            modifier = Modifier.weight(1f)
        )
        StatCard(
            label = "Profit Factor",
            value = perf?.profitFactor?.toString() ?: "N/A",
            modifier = Modifier.weight(1f),
            valueColor = BluePrimary
        )
    }
}

@Composable
private fun EquitySection(perf: com.aiscanner.app.data.api.Performance?) {
    val curve = perf?.equityCurve.orEmpty()
    if (curve.size >= 2) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = "P&L 7 hari: " + formatSignedPercent(perf?.pnlPct7d),
                style = MaterialTheme.typography.bodyMedium,
                color = if ((perf?.pnlPct7d ?: 0.0) >= 0) GreenPrimary else RedLoss
            )
            EquityChart(points = curve.mapNotNull { it.balance?.toFloat() })
        }
    } else {
        EmptyState(
            title = "Data equity belum cukup",
            subtitle = "Grafik muncul setelah bot mencatat transaksi tertutup.",
            accent = PurplePrimary
        )
    }
}

@Composable
private fun ActivityLogSection(logs: List<ApiService.LogItem>) {
    if (logs.isEmpty()) {
        EmptyState(
            title = "Belum ada aktivitas",
            subtitle = "Log aktivitas muncul saat bot mulai memindai market."
        )
        return
    }
    Column {
        logs.take(8).forEach { log ->
            ActivityLogItem(
                icon = log.icon ?: "•",
                message = log.message ?: "",
                time = log.time ?: ""
            )
        }
    }
}

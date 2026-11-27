package com.aiscanner.app.ui.screens.dashboard

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
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aiscanner.app.data.api.DashboardResponse
import com.aiscanner.app.ui.components.DisconnectedBanner
import com.aiscanner.app.ui.components.EmptyState
import com.aiscanner.app.ui.components.LoadingIndicator
import com.aiscanner.app.ui.components.StatCard
import com.aiscanner.app.ui.components.StatusBanner
import com.aiscanner.app.ui.screens.UiState
import com.aiscanner.app.ui.theme.AmberWarn
import com.aiscanner.app.ui.theme.BluePrimary
import com.aiscanner.app.ui.theme.GreenPrimary
import com.aiscanner.app.ui.theme.NavyCard
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

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    text = "AI SCANNER",
                    style = MaterialTheme.typography.headlineSmall,
                    color = TextPrimary,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "Full Trading Command Center",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary
                )
            }
            IconButton(onClick = { viewModel.load() }) {
                Icon(Icons.Filled.Refresh, contentDescription = "Refresh", tint = GreenPrimary)
            }
        }

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

            is UiState.Success -> DashboardContent((state as UiState.Success).data)
        }
    }
}

@Composable
private fun DashboardContent(data: DashboardResponse) {
    val bot = data.bot
    val portfolio = data.portfolio
    val perf = data.performance
    val sig = data.signals

    val paused = bot?.paused == true
    val health = bot?.health ?: "🟢 HEALTHY"

    StatusBanner(
        text = if (paused) {
            "PAPER TRADING — Bot dijeda: ${bot?.haltReason ?: ""}"
        } else {
            "PAPER TRADING — Mode utama aktif"
        },
        color = if (paused) AmberWarn else GreenPrimary
    )

    Spacer(Modifier.height(16.dp))

    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard(
            label = "Status Bot",
            value = health,
            modifier = Modifier.weight(1f),
            valueColor = if (health.contains("HALTED") || health.contains("CAUTION")) RedLoss else GreenPrimary
        )
        StatCard(
            label = "Last Scan",
            value = bot?.lastScan ?: "—",
            modifier = Modifier.weight(1f)
        )
    }

    Spacer(Modifier.height(12.dp))

    val equity = perf?.equityCurve?.lastOrNull()?.balance ?: portfolio?.balance ?: 0.0

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
            label = "Win Rate",
            value = if (perf?.winRate == null) "N/A" else formatPercent(perf.winRate),
            modifier = Modifier.weight(1f),
            valueColor = PurplePrimary
        )
        StatCard(
            label = "Profit Factor",
            value = perf?.profitFactor?.toString() ?: "N/A",
            modifier = Modifier.weight(1f),
            valueColor = BluePrimary
        )
    }

    Spacer(Modifier.height(12.dp))

    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard(
            label = "Max Drawdown",
            value = formatPercent(portfolio?.drawdownPct),
            modifier = Modifier.weight(1f),
            valueColor = if ((portfolio?.drawdownPct ?: 0.0) > 10.0) RedLoss else TextPrimary
        )
        StatCard(
            label = "Total Signals",
            value = formatInt(sig?.total),
            modifier = Modifier.weight(1f)
        )
    }

    Spacer(Modifier.height(12.dp))

    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard(
            label = "Open Trades",
            value = formatInt(portfolio?.openPositions),
            modifier = Modifier.weight(1f)
        )
        StatCard(
            label = "Closed Trades",
            value = if (perf?.totalTrades == null) "N/A" else formatInt(perf.totalTrades),
            modifier = Modifier.weight(1f)
        )
    }

    Spacer(Modifier.height(20.dp))

    Text(
        text = "Grafik Equity (7 hari)",
        style = MaterialTheme.typography.titleMedium,
        color = TextPrimary
    )
    Spacer(Modifier.height(8.dp))

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

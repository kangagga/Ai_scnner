package com.aiscanner.app.ui.screens.journal

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aiscanner.app.data.api.Trade
import com.aiscanner.app.ui.components.DisconnectedBanner
import com.aiscanner.app.ui.components.EmptyState
import com.aiscanner.app.ui.components.LoadingIndicator
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
import com.aiscanner.app.util.formatMoney
import com.aiscanner.app.util.formatNum
import com.aiscanner.app.util.formatPercent
import com.aiscanner.app.util.formatSignedMoney

@Composable
fun JournalScreen(viewModel: JournalViewModel) {
    val state by viewModel.uiState.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text(
            text = "Trading Journal",
            style = MaterialTheme.typography.headlineSmall,
            color = TextPrimary,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = "Riwayat virtual trading",
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary
        )
        Spacer(Modifier.height(12.dp))

        when (state) {
            is UiState.Loading -> LoadingIndicator()

            is UiState.Error -> {
                val err = state as UiState.Error
                if (err.disconnected) {
                    DisconnectedBanner()
                    Spacer(Modifier.height(16.dp))
                    EmptyState("Jurnal tidak tersedia", err.message)
                } else {
                    StatusBanner(text = err.message, color = RedLoss)
                }
            }

            is UiState.Success -> {
                val trades = (state as UiState.Success).data.trades.orEmpty()
                if (trades.isEmpty()) {
                    EmptyState(
                        title = "Belum ada transaksi",
                        subtitle = "Jurnal terisi otomatis saat bot menutup trade virtual.",
                        accent = PurplePrimary
                    )
                } else {
                    LazyColumn(
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                        modifier = Modifier.fillMaxSize()
                    ) {
                        items(trades, key = { it.id ?: it.hashCode().toLong() }) { trade ->
                            TradeCard(trade)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TradeCard(t: Trade) {
    val isWin = t.result?.equals("WIN", ignoreCase = true) == true
    val isLoss = t.result?.equals("LOSS", ignoreCase = true) == true
    val pnl = t.pnlUsd ?: 0.0
    val pnlColor = when {
        isWin -> GreenPrimary
        isLoss -> RedLoss
        pnl > 0 -> GreenPrimary
        pnl < 0 -> RedLoss
        else -> TextSecondary
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(NavyCard)
            .padding(14.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    text = t.pair ?: "—",
                    style = MaterialTheme.typography.titleMedium,
                    color = TextPrimary,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = (t.signal ?: "—") + " · " + (t.timeframe ?: "—"),
                    style = MaterialTheme.typography.labelSmall,
                    color = TextSecondary
                )
            }
            Text(
                text = formatSignedMoney(pnl),
                style = MaterialTheme.typography.titleMedium,
                color = pnlColor,
                fontWeight = FontWeight.Bold
            )
        }
        Spacer(Modifier.height(10.dp))

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            JournalCell("Entry", formatNum(t.entry))
            JournalCell("Exit", formatNum(t.exitPrice))
            JournalCell("P&L %", formatPercent(t.pnlPct))
        }
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            JournalCell("Hasil", t.result ?: "—")
            JournalCell("Biaya", formatMoney(t.fees))
            JournalCell("Durasi", durationText(t.durationMin))
        }

        if (!t.strategy.isNullOrBlank()) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Strategi: " + t.strategy,
                style = MaterialTheme.typography.bodyMedium,
                color = BluePrimary
            )
        }
        if (!t.entryReason.isNullOrBlank()) {
            Spacer(Modifier.height(4.dp))
            Text(
                text = "Alasan entry: " + t.entryReason,
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary
            )
        }
        if (!t.exitReason.isNullOrBlank()) {
            Spacer(Modifier.height(4.dp))
            Text(
                text = "Alasan exit: " + t.exitReason,
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary
            )
        }
    }
}

private fun durationText(min: Long?): String {
    val m = min ?: return "—"
    return if (m >= 60) {
        val h = m / 60
        val rem = m % 60
        if (rem == 0L) "${h}j" else "${h}j ${rem}m"
    } else {
        "${m}m"
    }
}

@Composable
private fun JournalCell(label: String, value: String) {
    Column(Modifier.weight(1f)) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = TextSecondary
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            color = TextPrimary,
            fontWeight = FontWeight.SemiBold
        )
    }
}

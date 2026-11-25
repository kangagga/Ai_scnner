package com.aiscanner.app.ui.screens.signals

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aiscanner.app.data.api.Signal
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
import com.aiscanner.app.util.formatInt
import com.aiscanner.app.util.formatNum
import com.aiscanner.app.util.formatPercent

private val FILTERS = listOf("Active", "Pending", "Accepted", "Rejected", "Expired")

@Composable
fun SignalsScreen(viewModel: SignalsViewModel) {
    val state by viewModel.uiState.collectAsState()
    val filter by viewModel.filter.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text(
            text = "Signal Intelligence",
            style = MaterialTheme.typography.headlineSmall,
            color = TextPrimary,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = "Daftar sinyal dari mesin scanner",
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary
        )
        Spacer(Modifier.height(12.dp))

        // Filter chips
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            FILTERS.forEach { f ->
                val selected = filter == f
                val chipColor = if (selected) BluePrimary else NavyCard
                Column(
                    modifier = Modifier
                        .clip(RoundedCornerShape(20.dp))
                        .background(chipColor)
                        .padding(horizontal = 14.dp, vertical = 7.dp)
                ) {
                    Text(
                        text = f,
                        style = MaterialTheme.typography.labelMedium,
                        color = if (selected) TextPrimary else TextSecondary,
                        fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium
                    )
                }
            }
        }
        Spacer(Modifier.height(12.dp))

        when (state) {
            is UiState.Loading -> LoadingIndicator()

            is UiState.Error -> {
                val err = state as UiState.Error
                if (err.disconnected) {
                    DisconnectedBanner()
                    Spacer(Modifier.height(16.dp))
                    EmptyState("Sinyal tidak tersedia", err.message)
                } else {
                    StatusBanner(text = err.message, color = RedLoss)
                }
            }

            is UiState.Success -> {
                val all = (state as UiState.Success).data
                val filtered = all.filter { effectiveStatus(it) == filter }
                if (filtered.isEmpty()) {
                    EmptyState(
                        title = "Tidak ada sinyal ($filter)",
                        subtitle = if (all.isEmpty()) "Belum ada sinyal dari scanner." else "Tidak ada sinyal dengan status $filter."
                    )
                } else {
                    LazyColumn(
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                        modifier = Modifier.fillMaxSize()
                    ) {
                        items(filtered, key = { it.symbol + it.timeframe + it.signal }) { signal ->
                            SignalCard(signal)
                        }
                    }
                }
            }
        }
    }
}

private fun effectiveStatus(s: Signal): String {
    val raw = s.status?.trim().orEmpty()
    return when {
        raw.isEmpty() -> "Active"
        raw.equals("active", ignoreCase = true) -> "Active"
        raw.equals("pending", ignoreCase = true) -> "Pending"
        raw.equals("accepted", ignoreCase = true) -> "Accepted"
        raw.equals("rejected", ignoreCase = true) -> "Rejected"
        raw.equals("expired", ignoreCase = true) -> "Expired"
        else -> "Active"
    }
}

@Composable
private fun SignalCard(s: Signal) {
    val isBuy = s.signal?.contains("BUY", ignoreCase = true) == true
    val sigColor = if (isBuy) GreenPrimary else RedLoss

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(NavyCard)
            .padding(14.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = s.symbol ?: "—",
                style = MaterialTheme.typography.titleMedium,
                color = TextPrimary,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f)
            )
            Text(
                text = s.timeframe ?: "—",
                style = MaterialTheme.typography.labelMedium,
                color = TextSecondary
            )
            Spacer(Modifier.width(8.dp))
            Text(
                text = s.signal ?: "—",
                style = MaterialTheme.typography.labelMedium,
                color = sigColor,
                fontWeight = FontWeight.Bold
            )
        }
        Spacer(Modifier.height(10.dp))

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            DetailCell("Harga", formatNum(s.price))
            DetailCell("Entry", formatNum(s.entry))
            DetailCell("SL", formatNum(s.sl))
        }
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            DetailCell("TP1", formatNum(s.tp1))
            DetailCell("R/R", s.rrRatio?.toString() ?: "—")
            DetailCell("Confidence", formatPercent(s.confidence))
        }
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            DetailCell("Win Rate", formatPercent(s.winRate))
            DetailCell("Status", effectiveStatus(s))
        }

        if (!s.reason.isNullOrBlank()) {
            Spacer(Modifier.height(10.dp))
            Text(
                text = s.reason,
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary
            )
        }
    }
}

@Composable
private fun DetailCell(label: String, value: String) {
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

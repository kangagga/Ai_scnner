package com.aiscanner.app.ui.screens.learning

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aiscanner.app.ui.components.DemoBanner
import com.aiscanner.app.ui.components.DisconnectedBanner
import com.aiscanner.app.ui.components.EmptyState
import com.aiscanner.app.ui.components.LoadingIndicator
import com.aiscanner.app.ui.components.StatCard
import com.aiscanner.app.ui.components.StatusBanner
import com.aiscanner.app.ui.screens.UiState
import com.aiscanner.app.ui.screens.learning.LearningViewModel.SetupPerf
import com.aiscanner.app.ui.theme.AmberWarn
import com.aiscanner.app.ui.theme.BluePrimary
import com.aiscanner.app.ui.theme.GreenPrimary
import com.aiscanner.app.ui.theme.NavyCard
import com.aiscanner.app.ui.theme.PurplePrimary
import com.aiscanner.app.ui.theme.RedLoss
import com.aiscanner.app.ui.theme.TextPrimary
import com.aiscanner.app.ui.theme.TextSecondary
import com.aiscanner.app.util.formatInt
import com.aiscanner.app.util.formatPercent
import com.aiscanner.app.util.formatSignedPercent

@Composable
fun LearningScreen(viewModel: LearningViewModel) {
    val state by viewModel.uiState.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        Text(
            text = "AI Learning",
            style = MaterialTheme.typography.headlineSmall,
            color = TextPrimary,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = "Evaluasi strategi berbasis data nyata",
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
                    EmptyState("Data learning tidak tersedia", err.message)
                } else {
                    StatusBanner(text = err.message, color = RedLoss)
                }
            }

            is UiState.Success -> LearningContent((state as UiState.Success).data)
        }
    }
}

@Composable
private fun LearningContent(data: LearningViewModel.LearningData) {
    val perf = data.overall?.performance
    val portfolio = data.overall?.portfolio

    Text(
        text = "Evaluasi Keseluruhan",
        style = MaterialTheme.typography.titleMedium,
        color = TextPrimary
    )
    Spacer(Modifier.height(8.dp))

    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("Win Rate", formatPercent(perf?.winRate), Modifier.weight(1f), valueColor = PurplePrimary)
        StatCard("Profit Factor", (perf?.profitFactor ?: 0.0).toString(), Modifier.weight(1f), valueColor = BluePrimary)
    }
    Spacer(Modifier.height(12.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("Total Trades", formatInt(perf?.totalTrades), Modifier.weight(1f))
        StatCard("Jumlah Rugi", formatInt(data.totalLosses), Modifier.weight(1f), valueColor = if (data.totalLosses > 0) RedLoss else GreenPrimary)
    }

    Spacer(Modifier.height(20.dp))

    Text(
        text = "Performa per Setup",
        style = MaterialTheme.typography.titleMedium,
        color = TextPrimary
    )
    Spacer(Modifier.height(8.dp))

    if (data.setups.isEmpty()) {
        EmptyState(
            title = "Belum ada data setup",
            subtitle = "Performa per strategi muncul setelah ada transaksi tertutup.",
            accent = PurplePrimary
        )
    } else {
        data.setups.forEach { setup ->
            SetupRow(setup)
            Spacer(Modifier.height(8.dp))
        }
    }

    Spacer(Modifier.height(16.dp))

    Text(
        text = "Analisis Kerugian",
        style = MaterialTheme.typography.titleMedium,
        color = TextPrimary
    )
    Spacer(Modifier.height(8.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("Rata-rata Rugi", formatSignedPercent(data.avgLossPct), Modifier.weight(1f), valueColor = RedLoss)
        StatCard("Max Drawdown", formatPercent(portfolio?.drawdownPct), Modifier.weight(1f), valueColor = if ((portfolio?.drawdownPct ?: 0.0) > 10.0) RedLoss else TextPrimary)
    }

    Spacer(Modifier.height(16.dp))

    Text(
        text = "Rekomendasi Berbasis Data",
        style = MaterialTheme.typography.titleMedium,
        color = TextPrimary
    )
    Spacer(Modifier.height(8.dp))

    val best = data.bestSetup
    if (best != null && best.count >= 3) {
        InfoCard(
            title = "Setup terbaik saat ini",
            body = "Strategi \"${best.strategy}\" memiliki win rate ${formatPercent(best.winRate)} dari ${best.count} transaksi. Pertimbangkan untuk fokus pada setup ini, sambil tetap mematuhi risk management."
        )
    } else {
        InfoCard(
            title = "Data belum cukup",
            body = "Dibutuhkan minimal 3 transaksi per setup untuk rekomendasi yang andal. AI hanya memberi rekomendasi, tidak mengubah strategi produksi otomatis."
        )
    }

    Spacer(Modifier.height(16.dp))
    DemoBanner(
        text = "DEMO — Narasi analisis AI (Gemini) untuk evaluasi keterlambatan entry belum terhubung. Semua angka di atas adalah data nyata dari jurnal trading."
    )
}

@Composable
private fun SetupRow(setup: SetupPerf) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(NavyCard)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
    ) {
        Text(
            text = setup.strategy,
            style = MaterialTheme.typography.bodyLarge,
            color = TextPrimary,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.weight(1f)
        )
        Text(
            text = "${setup.wins}/${setup.count}",
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary
        )
        Spacer(Modifier.padding(horizontal = 8.dp))
        Text(
            text = formatPercent(setup.winRate),
            style = MaterialTheme.typography.titleMedium,
            color = if (setup.winRate >= 50) GreenPrimary else RedLoss,
            fontWeight = FontWeight.Bold
        )
    }
}

@Composable
private fun InfoCard(title: String, body: String) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(NavyCard)
            .padding(14.dp)
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            color = TextPrimary
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = body,
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary
        )
    }
}

package com.aiscanner.app.ui.screens.analyst

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
import com.aiscanner.app.data.api.MarketAnalysis
import com.aiscanner.app.ui.components.DemoBanner
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
import com.aiscanner.app.util.formatNum

@Composable
fun AnalystScreen(viewModel: AnalystViewModel) {
    val state by viewModel.uiState.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        Text(
            text = "AI Market Analyst",
            style = MaterialTheme.typography.headlineSmall,
            color = TextPrimary,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = "Analisis kondisi pasar global",
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
                    EmptyState("Analisis tidak tersedia", err.message)
                } else {
                    StatusBanner(text = err.message, color = RedLoss)
                }
            }

            is UiState.Success -> AnalystContent((state as UiState.Success).data)
        }
    }
}

@Composable
private fun AnalystContent(data: MarketAnalysis) {
    val regime = data.regime ?: "NEUTRAL"
    val regimeColor = when {
        regime.equals("BULLISH", ignoreCase = true) -> GreenPrimary
        regime.equals("BEARISH", ignoreCase = true) -> RedLoss
        else -> AmberWarn
    }

    StatusBanner(
        text = "Kondisi Market: $regime",
        color = regimeColor
    )

    Spacer(Modifier.height(16.dp))

    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("BTC Trend", data.btcTrend ?: "—", Modifier.weight(1f), valueColor = BluePrimary)
        StatCard("Kekuatan", data.btcStrength ?: "—", Modifier.weight(1f))
    }

    Spacer(Modifier.height(12.dp))

    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("BTC Harga", formatNum(data.btcPrice), Modifier.weight(1f))
        StatCard("ADX", formatNum(data.btcAdx), Modifier.weight(1f))
    }

    Spacer(Modifier.height(12.dp))

    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("Fear & Greed", formatInt(data.fearGreedValue), Modifier.weight(1f), valueColor = PurplePrimary)
        StatCard("Label", data.fearGreedLabel ?: "—", Modifier.weight(1f))
    }

    Spacer(Modifier.height(12.dp))

    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("Izin BUY", if (data.allowBuy == true) "Diizinkan" else "Diblokir", Modifier.weight(1f), valueColor = if (data.allowBuy == true) GreenPrimary else RedLoss)
        StatCard("Izin SELL", if (data.allowSell == true) "Diizinkan" else "Diblokir", Modifier.weight(1f), valueColor = if (data.allowSell == true) GreenPrimary else RedLoss)
    }

    if (!data.summary.isNullOrBlank()) {
        Spacer(Modifier.height(16.dp))
        InfoCard("Ringkasan", data.summary)
    }

    if (!data.aiExplanation.isNullOrBlank()) {
        Spacer(Modifier.height(12.dp))
        InfoCard("Penjelasan AI", data.aiExplanation)
    }

    Spacer(Modifier.height(16.dp))
    Text(
        text = "Detail Setup",
        style = MaterialTheme.typography.titleMedium,
        color = TextPrimary
    )
    Spacer(Modifier.height(8.dp))
    DemoBanner(
        text = "DEMO — Detail support/resistance, base formation, retest, breakout, dan rejection belum tersedia dari backend. Tidak ada data palsu yang ditampilkan."
    )
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

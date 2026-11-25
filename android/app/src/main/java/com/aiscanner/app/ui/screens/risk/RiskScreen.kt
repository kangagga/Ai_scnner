package com.aiscanner.app.ui.screens.risk

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
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
fun RiskScreen(viewModel: RiskViewModel) {
    val state by viewModel.uiState.collectAsState()
    val controlKey by viewModel.controlKey.collectAsState()
    val actionState by viewModel.actionState.collectAsState()
    val running = actionState == "running"

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        Text(
            text = "Risk Control",
            style = MaterialTheme.typography.headlineSmall,
            color = TextPrimary,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = "Keamanan & batas risiko",
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
                    EmptyState("Status risiko tidak tersedia", err.message)
                } else {
                    StatusBanner(text = err.message, color = RedLoss)
                }
            }

            is UiState.Success -> RiskContent(
                data = (state as UiState.Success).data,
                controlKey = controlKey,
                onKeyChange = viewModel::setControlKey,
                running = running,
                actionState = actionState,
                onPause = viewModel::pause,
                onResume = viewModel::resume,
                onEmergency = viewModel::emergencyStop
            )
        }
    }
}

@Composable
private fun RiskContent(
    data: com.aiscanner.app.data.api.RiskStatus,
    controlKey: String,
    onKeyChange: (String) -> Unit,
    running: Boolean,
    actionState: String?,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onEmergency: () -> Unit
) {
    val halted = data.tradingHalted == true
    val health = data.health ?: "🟢 HEALTHY"

    StatusBanner(
        text = if (halted) "⛔ Trading DIHENTIKAN: ${data.haltReason ?: ""}" else "Status Keamanan: $health",
        color = if (halted) RedLoss else GreenPrimary
    )

    Spacer(Modifier.height(16.dp))

    Text(
        text = "Batas Risiko",
        style = MaterialTheme.typography.titleMedium,
        color = TextPrimary
    )
    Spacer(Modifier.height(8.dp))

    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("Max Drawdown", formatPercent(data.limits?.maxDrawdownPct), Modifier.weight(1f), valueColor = PurplePrimary)
        StatCard("Max Rugi Harian", formatPercent(data.limits?.maxDailyLossPct), Modifier.weight(1f), valueColor = RedLoss)
    }
    Spacer(Modifier.height(12.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("Max Posisi", formatInt(data.maxPositions), Modifier.weight(1f))
        StatCard("Max Portfolio Heat", formatPercent(data.limits?.maxHeatPct), Modifier.weight(1f), valueColor = AmberWarn)
    }

    Spacer(Modifier.height(20.dp))

    Text(
        text = "Kondisi Saat Ini",
        style = MaterialTheme.typography.titleMedium,
        color = TextPrimary
    )
    Spacer(Modifier.height(8.dp))

    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("Balance", formatMoney(data.balance), Modifier.weight(1f), valueColor = GreenPrimary)
        StatCard("Drawdown", formatPercent(data.drawdownPct), Modifier.weight(1f), valueColor = if ((data.drawdownPct ?: 0.0) > 10.0) RedLoss else TextPrimary)
    }
    Spacer(Modifier.height(12.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("PnL Harian", formatSignedMoney(data.dailyPnl), Modifier.weight(1f), valueColor = if ((data.dailyPnl ?: 0.0) >= 0) GreenPrimary else RedLoss, sub = formatSignedPercent(data.dailyPnlPct))
        StatCard("Heat", formatPercent(data.portfolioHeat), Modifier.weight(1f), valueColor = if ((data.portfolioHeat ?: 0.0) > 15.0) AmberWarn else TextPrimary)
    }
    Spacer(Modifier.height(12.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("Open Posisi", formatInt(data.openPositions), Modifier.weight(1f))
        StatCard("Rugi Beruntun", formatInt(data.consecutiveLoss), Modifier.weight(1f), valueColor = if ((data.consecutiveLoss ?: 0) >= 3) RedLoss else TextPrimary)
    }

    Spacer(Modifier.height(20.dp))

    Text(
        text = "Kontrol Bot",
        style = MaterialTheme.typography.titleMedium,
        color = TextPrimary
    )
    Spacer(Modifier.height(8.dp))

    DemoBanner(
        text = "Tombol kontrol hanya berfungsi jika backend memiliki endpoint aman & tervalidasi (memerlukan X-API-Key). Tidak ada tombol live order."
    )
    Spacer(Modifier.height(12.dp))

    OutlinedTextField(
        value = controlKey,
        onValueChange = onKeyChange,
        label = { Text("API Control Key (X-API-Key)") },
        singleLine = true,
        modifier = Modifier.fillMaxWidth()
    )

    Spacer(Modifier.height(16.dp))

    Button(
        onClick = onPause,
        enabled = !running && controlKey.isNotBlank(),
        modifier = Modifier.fillMaxWidth(),
        colors = ButtonDefaults.buttonColors(containerColor = AmberWarn)
    ) {
        Text("⏸ Pause Bot", fontWeight = FontWeight.SemiBold)
    }
    Spacer(Modifier.height(10.dp))

    Button(
        onClick = onResume,
        enabled = !running && controlKey.isNotBlank(),
        modifier = Modifier.fillMaxWidth(),
        colors = ButtonDefaults.buttonColors(containerColor = GreenPrimary)
    ) {
        Text("▶️ Resume Bot", fontWeight = FontWeight.SemiBold)
    }
    Spacer(Modifier.height(10.dp))

    Button(
        onClick = onEmergency,
        enabled = !running && controlKey.isNotBlank(),
        modifier = Modifier.fillMaxWidth(),
        colors = ButtonDefaults.buttonColors(containerColor = RedLoss)
    ) {
        Text("🛑 Emergency Stop", fontWeight = FontWeight.SemiBold)
    }

    if (running) {
        Spacer(Modifier.height(16.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center
        ) {
            CircularProgressIndicator(color = GreenPrimary, strokeWidth = 3.dp)
        }
    }

    if (actionState != null && actionState != "running") {
        Spacer(Modifier.height(16.dp))
        if (actionState.startsWith("ok:")) {
            StatusBanner(text = "Perintah berhasil: ${actionState.removePrefix("ok:")}", color = GreenPrimary)
        } else {
            StatusBanner(text = "Gagal: ${actionState.removePrefix("error:")}", color = RedLoss)
        }
    }
}

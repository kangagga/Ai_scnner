package com.aiscanner.app.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.aiscanner.app.ui.theme.AmberWarn
import com.aiscanner.app.ui.theme.BluePrimary
import com.aiscanner.app.ui.theme.GreenPrimary
import com.aiscanner.app.ui.theme.NavyCard
import com.aiscanner.app.ui.theme.NeonCyan
import com.aiscanner.app.ui.theme.RedLoss
import com.aiscanner.app.ui.theme.TextPrimary
import com.aiscanner.app.ui.theme.TextSecondary

@Composable
fun SectionTitle(title: String, modifier: Modifier = Modifier) {
    Text(
        text = title,
        style = MaterialTheme.typography.titleMedium,
        color = TextPrimary,
        fontWeight = FontWeight.SemiBold,
        modifier = modifier.padding(bottom = 8.dp)
    )
}

@Composable
fun StatCard(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    valueColor: Color = TextPrimary,
    sub: String? = null
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(18.dp))
            .background(NavyCard)
            .padding(14.dp)
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = TextSecondary
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = value,
            style = MaterialTheme.typography.titleLarge,
            color = valueColor,
            fontWeight = FontWeight.Bold
        )
        if (sub != null) {
            Spacer(Modifier.height(2.dp))
            Text(
                text = sub,
                style = MaterialTheme.typography.labelSmall,
                color = TextSecondary
            )
        }
    }
}

@Composable
fun StatusBanner(
    text: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(color.copy(alpha = 0.14f))
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(RoundedCornerShape(5.dp))
                .background(color)
        )
        Spacer(Modifier.width(10.dp))
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = color,
            fontWeight = FontWeight.SemiBold
        )
    }
}

@Composable
fun DisconnectedBanner(modifier: Modifier = Modifier) {
    StatusBanner(
        text = "DISCONNECTED — Tidak terhubung ke server bot. Data tidak tersedia.",
        color = RedLoss,
        modifier = modifier
    )
}

@Composable
fun DemoBanner(modifier: Modifier = Modifier, text: String = "DEMO — Data belum tersedia dari backend. Tidak ada data palsu yang ditampilkan.") {
    StatusBanner(text = text, color = AmberWarn, modifier = modifier)
}

@Composable
fun LoadingIndicator(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier.fillMaxWidth().padding(32.dp),
        contentAlignment = Alignment.Center
    ) {
        CircularProgressIndicator(color = BluePrimary, strokeWidth = 3.dp)
    }
}

@Composable
fun EmptyState(
    title: String,
    subtitle: String,
    modifier: Modifier = Modifier,
    accent: Color = BluePrimary
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(vertical = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Box(
            modifier = Modifier
                .size(48.dp)
                .clip(RoundedCornerShape(14.dp))
                .background(accent.copy(alpha = 0.15f)),
            contentAlignment = Alignment.Center
        ) {
            Text("○", color = accent, style = MaterialTheme.typography.titleLarge)
        }
        Spacer(Modifier.height(12.dp))
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            color = TextPrimary,
            textAlign = TextAlign.Center
        )
        Spacer(Modifier.height(4.dp))
        Text(
            text = subtitle,
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary,
            textAlign = TextAlign.Center
        )
    }
}

// ── Bot Status Panel ─────────────────────────────────────────────────────────

@Composable
fun BotStatusPanel(
    running: Boolean,
    paperMode: Boolean,
    modifier: Modifier = Modifier
) {
    val statusColor = if (running) GreenPrimary else RedLoss
    val statusText = if (running) "BOT BERJALAN" else "BOT BERHENTI"

    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(NavyCard)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(12.dp)
                .clip(CircleShape)
                .background(statusColor)
        )
        Spacer(Modifier.width(12.dp))
        Text(
            text = statusText,
            style = MaterialTheme.typography.titleMedium,
            color = statusColor,
            fontWeight = FontWeight.Bold
        )
        Spacer(Modifier.weight(1f))
        if (paperMode) {
            Text(
                text = "PAPER TRADING",
                style = MaterialTheme.typography.labelSmall,
                color = NeonCyan,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .background(NeonCyan.copy(alpha = 0.12f))
                    .padding(horizontal = 10.dp, vertical = 4.dp)
            )
        }
    }
}

// ── Live Crypto Scanner ──────────────────────────────────────────────────────

/** Radar lingkaran beranimasi. Hanya berputar ketika `scanning == true`. */
@Composable
fun ScannerRadar(
    scanning: Boolean,
    modifier: Modifier = Modifier,
    size: Int = 120
) {
    val sweep = rememberInfiniteTransition(label = "radar")
    val angle by sweep.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 2200, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "sweep"
    )

    Box(
        modifier = modifier.size(size.dp),
        contentAlignment = Alignment.Center
    ) {
        Canvas(modifier = Modifier.size(size.dp)) {
            val radius = this.size.minDimension / 2f
            val center = Offset(this.size.width / 2f, this.size.height / 2f)
            // Outer ring
            drawCircle(color = NeonCyan.copy(alpha = 0.35f), radius = radius, style = Stroke(width = 2.dp.toPx()))
            // Inner ring
            drawCircle(color = NeonCyan.copy(alpha = 0.18f), radius = radius * 0.62f, style = Stroke(width = 1.5f))
            // Crosshair
            drawLine(
                color = NeonCyan.copy(alpha = 0.18f),
                start = Offset(center.x, 0f),
                end = Offset(center.x, this.size.height),
                strokeWidth = 1f
            )
            drawLine(
                color = NeonCyan.copy(alpha = 0.18f),
                start = Offset(0f, center.y),
                end = Offset(this.size.width, center.y),
                strokeWidth = 1f
            )
            // Sweep beam
            if (scanning) {
                val rad = Math.toRadians(angle.toDouble())
                val sweepX = center.x + kotlin.math.cos(rad).toFloat() * radius
                val sweepY = center.y + kotlin.math.sin(rad).toFloat() * radius
                drawLine(
                    color = NeonCyan.copy(alpha = 0.7f),
                    start = center,
                    end = Offset(sweepX, sweepY),
                    strokeWidth = 2.5f,
                    cap = StrokeCap.Round
                )
            }
        }
        // Ikon tengah
        Text(
            text = "◎",
            color = if (scanning) NeonCyan else TextSecondary,
            style = MaterialTheme.typography.titleLarge
        )
    }
}

@Composable
fun ScannerProgressBar(
    progress: Float?,
    scanning: Boolean,
    modifier: Modifier = Modifier
) {
    val pct = (progress ?: 0f).coerceIn(0f, 100f)
    Column(modifier = modifier.fillMaxWidth()) {
        LinearProgressIndicator(
            progress = { pct / 100f },
            modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
            color = NeonCyan,
            trackColor = NavyCardElevated
        )
        Spacer(Modifier.height(6.dp))
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(
                text = if (scanning) "Memindai..." else "Standby",
                style = MaterialTheme.typography.labelSmall,
                color = if (scanning) NeonCyan else TextSecondary
            )
            if (progress != null) {
                Text(
                    text = "${pct.toInt()}%",
                    style = MaterialTheme.typography.labelSmall,
                    color = TextSecondary
                )
            }
        }
    }
}

// ── Market Overview ──────────────────────────────────────────────────────────

@Composable
fun MarketAssetCard(
    symbol: String,
    pair: String,
    price: String,
    changePct: String,
    changePositive: Boolean,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(18.dp))
            .background(NavyCard)
            .padding(14.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = symbol,
                style = MaterialTheme.typography.titleMedium,
                color = TextPrimary,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.weight(1f))
            Text(
                text = changePct,
                style = MaterialTheme.typography.labelMedium,
                color = if (changePositive) GreenPrimary else RedLoss,
                fontWeight = FontWeight.SemiBold
            )
        }
        Spacer(Modifier.height(4.dp))
        Text(
            text = pair,
            style = MaterialTheme.typography.labelSmall,
            color = TextSecondary
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = price,
            style = MaterialTheme.typography.titleLarge,
            color = TextPrimary,
            fontWeight = FontWeight.Bold
        )
    }
}

// ── Activity Log ─────────────────────────────────────────────────────────────

@Composable
fun ActivityLogItem(
    icon: String,
    message: String,
    time: String,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth().padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = icon,
            style = MaterialTheme.typography.titleMedium,
            color = NeonCyan
        )
        Spacer(Modifier.width(10.dp))
        Text(
            text = message,
            style = MaterialTheme.typography.bodyMedium,
            color = TextPrimary,
            modifier = Modifier.weight(1f)
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = time,
            style = MaterialTheme.typography.labelSmall,
            color = TextSecondary
        )
    }
}

// ── Signal Monitor Row ───────────────────────────────────────────────────────

@Composable
fun SignalMonitorRow(
    direction: String,
    symbol: String,
    timeframe: String,
    confidence: String?,
    time: String,
    modifier: Modifier = Modifier
) {
    val isBuy = direction.contains("BUY", ignoreCase = true)
    val isSell = direction.contains("SELL", ignoreCase = true)
    val dirColor = when {
        isBuy -> GreenPrimary
        isSell -> RedLoss
        else -> BluePrimary
    }
    val dirIcon = when {
        isBuy -> "▲"
        isSell -> "▼"
        else -> "●"
    }

    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(NavyCard)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = dirIcon,
            style = MaterialTheme.typography.titleMedium,
            color = dirColor,
            fontWeight = FontWeight.Bold
        )
        Spacer(Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = symbol,
                style = MaterialTheme.typography.titleSmall,
                color = TextPrimary,
                fontWeight = FontWeight.SemiBold
            )
            Text(
                text = "$direction • $timeframe",
                style = MaterialTheme.typography.labelSmall,
                color = TextSecondary
            )
        }
        if (confidence != null) {
            Text(
                text = confidence,
                style = MaterialTheme.typography.labelMedium,
                color = dirColor,
                fontWeight = FontWeight.SemiBold
            )
        }
    }
}

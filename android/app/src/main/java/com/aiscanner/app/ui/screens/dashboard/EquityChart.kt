package com.aiscanner.app.ui.screens.dashboard

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.unit.dp
import com.aiscanner.app.ui.theme.NeonCyan
import com.aiscanner.app.ui.theme.TextSecondary
import com.patrykandpatrick.vico.compose.cartesian.CartesianChartHost
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberBottom
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberStart
import com.patrykandpatrick.vico.compose.cartesian.layer.rememberLineCartesianLayer
import com.patrykandpatrick.vico.compose.cartesian.rememberCartesianChart
import com.patrykandpatrick.vico.core.cartesian.axis.HorizontalAxis
import com.patrykandpatrick.vico.core.cartesian.axis.VerticalAxis
import com.patrykandpatrick.vico.core.cartesian.data.CartesianChartModelProducer
import com.patrykandpatrick.vico.core.cartesian.data.lineSeries
import com.patrykandpatrick.vico.core.cartesian.layer.LineCartesianLayer

@Composable
fun EquityChart(points: List<Float>, modifier: Modifier = Modifier) {
    val modelProducer = remember { CartesianChartModelProducer() }

    LaunchedEffect(points) {
        if (points.size >= 2) {
            modelProducer.runTransaction {
                lineSeries { series(points) }
            }
        }
    }

    val lineLayer = rememberLineCartesianLayer(
        lineProvider = LineCartesianLayer.LineProvider.series(
            LineCartesianLayer.LineProvider.Series(
                lineColor = NeonCyan,
                areaFill = SolidColor(NeonCyan.copy(alpha = 0.12f))
            )
        )
    )

    val chart = rememberCartesianChart(
        lineLayer,
        startAxis = VerticalAxis.Companion.rememberStart(labelColor = TextSecondary),
        bottomAxis = HorizontalAxis.Companion.rememberBottom(labelColor = TextSecondary)
    )

    CartesianChartHost(
        chart = chart,
        modelProducer = modelProducer,
        modifier = modifier.fillMaxWidth().height(180.dp)
    )
}

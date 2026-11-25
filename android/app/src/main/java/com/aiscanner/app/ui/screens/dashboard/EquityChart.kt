package com.aiscanner.app.ui.screens.dashboard

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.patrykandpatrick.vico.compose.cartesian.CartesianChartHost
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberBottomAxis
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberStartAxis
import com.patrykandpatrick.vico.compose.cartesian.layer.rememberLineCartesianLayer
import com.patrykandpatrick.vico.compose.cartesian.rememberCartesianChart
import com.patrykandpatrick.vico.compose.cartesian.rememberCartesianChartModelProducer
import com.patrykandpatrick.vico.core.cartesian.data.lineSeries

@Composable
fun EquityChart(points: List<Float>, modifier: Modifier = Modifier) {
    val modelProducer = rememberCartesianChartModelProducer()

    LaunchedEffect(points) {
        if (points.size >= 2) {
            modelProducer.runTransaction {
                lineSeries {
                    series(points.map { it as Number })
                }
            }
        }
    }

    val chart = rememberCartesianChart(
        layer = rememberLineCartesianLayer(),
        startAxis = rememberStartAxis(),
        bottomAxis = rememberBottomAxis()
    )

    CartesianChartHost(
        chart = chart,
        modelProducer = modelProducer,
        modifier = modifier.fillMaxWidth().height(180.dp)
    )
}

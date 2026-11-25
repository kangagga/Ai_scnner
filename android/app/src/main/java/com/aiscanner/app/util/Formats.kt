package com.aiscanner.app.util

import java.text.DecimalFormat
import kotlin.math.abs

private val moneyFmt = DecimalFormat("#,##0.00")
private val pctFmt = DecimalFormat("#,##0.0")
private val numFmt = DecimalFormat("#,##0.##")

fun formatMoney(v: Double?): String = "$" + moneyFmt.format(v ?: 0.0)

fun formatSignedMoney(v: Double?): String {
    val d = v ?: 0.0
    val sign = if (d >= 0) "+" else "-"
    return sign + "$" + moneyFmt.format(abs(d))
}

fun formatPercent(v: Double?): String = pctFmt.format(v ?: 0.0) + "%"

fun formatSignedPercent(v: Double?): String {
    val d = v ?: 0.0
    val sign = if (d >= 0) "+" else "-"
    return sign + pctFmt.format(abs(d)) + "%"
}

fun formatInt(v: Int?): String = (v ?: 0).toString()

fun formatNum(v: Double?): String = numFmt.format(v ?: 0.0)

package com.aiscanner.app.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.aiscanner.app.data.api.Signal

@Entity(tableName = "signals_cache")
data class SignalEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val symbol: String? = null,
    val timeframe: String? = null,
    val signal: String? = null,
    val price: Double? = null,
    val entry: Double? = null,
    val sl: Double? = null,
    val tp1: Double? = null,
    val tp2: Double? = null,
    val tp3: Double? = null,
    val rrRatio: Double? = null,
    val confidence: Double? = null,
    val score: Double? = null,
    val winRate: Double? = null,
    val reason: String? = null,
    val status: String? = null,
    val candlePattern: String? = null,
    val support: Double? = null,
    val resistance: Double? = null,
    val volRatio: Double? = null,
    val rsi: Double? = null,
    val cachedAt: Long = System.currentTimeMillis()
)

fun Signal.toEntity(): SignalEntity = SignalEntity(
    symbol = symbol,
    timeframe = timeframe,
    signal = signal,
    price = price,
    entry = entry,
    sl = sl,
    tp1 = tp1,
    tp2 = tp2,
    tp3 = tp3,
    rrRatio = rrRatio,
    confidence = confidence,
    score = score,
    winRate = winRate,
    reason = reason,
    status = status,
    candlePattern = candlePattern,
    support = support,
    resistance = resistance,
    volRatio = volRatio,
    rsi = rsi
)

fun SignalEntity.toSignal(): Signal = Signal(
    symbol = symbol,
    timeframe = timeframe,
    signal = signal,
    price = price,
    entry = entry,
    sl = sl,
    tp1 = tp1,
    tp2 = tp2,
    tp3 = tp3,
    rrRatio = rrRatio,
    confidence = confidence,
    score = score,
    winRate = winRate,
    reason = reason,
    status = status,
    candlePattern = candlePattern,
    support = support,
    resistance = resistance,
    volRatio = volRatio,
    rsi = rsi
)

package com.aiscanner.app.data.api

import retrofit2.http.GET

/** Semua endpoint GET read-only. Tidak ada kontrol bot / order. */
interface ApiService {
    @GET("api/health") suspend fun health(): Health
    @GET("api/status") suspend fun status(): Status
    @GET("api/signals") suspend fun signals(): List<Signal>
    @GET("api/portfolio") suspend fun portfolio(): RiskStatus
    @GET("api/market_regime") suspend fun marketRegime(): MarketAnalysis

    data class Health(val ok: Boolean?, val time: String?)
    data class Status(
        val bot_start: String?, val config: Map<String, Any>?, val cooldowns: Map<String, Any>?,
        val last_scan: String?, val logs: List<LogItem>?, val scan_progress: ScanProgress?,
        val stats: Stats?, val bot: BotStatus?
    )
    data class LogItem(val icon: String?, val message: String?, val time: String?)
    data class ScanProgress(val pct: Float?, val current: String?, val done: Int?, val total: Int?)
    data class Stats(val total: Int?, val buy: Int?, val sell: Int?, val avg_wr: Float?, val avg_score: Float?)
    data class BotStatus(
        val mode: String?, val mirror_enabled: Boolean?, val running: Boolean?, val connected: Boolean?,
        val last_scan: String?, val bot_start: String?, val health: String?, val balance: Double?,
        val peak_balance: Double?, val drawdown_pct: Float?, val open_positions: Int?,
        val total_trades: Int?, val paused: Boolean?, val halt_reason: String?
    )
}

package com.aiscanner.app.data.api

import com.aiscanner.app.data.model.Signal
import retrofit2.GET
import retrofit2.http.GET
import java.util.Map

interface ApiService {
    @GET("api/health")
    suspend fun health(): ApiResponse.Health

    @GET("api/status")
    suspend fun status(): ApiResponse.Status

    @GET("api/signals")
    suspend fun signals(): List<Signal>

    data class ApiResponse {
        data class Health(val ok: Boolean, val time: String)
        data class Status(
            val bot_start: String?,
            val config: Map<String, Any>?,
            val cooldowns: Map<String, Any>?,
            val last_scan: String?,
            val logs: List<LogItem>?,
            val scan_progress: ScanProgress?,
            val stats: Stats?,
            val bot: BotStatus?
        )
        data class LogItem(val icon: String, val message: String, val time: String)
        data class ScanProgress(val pct: Float, val current: String, val done: Int, val total: Int)
        data class Stats(val total: Int, val buy: Int, val sell: Int, val avg_wr: Float, val avg_score: Float)
        data class BotStatus(
            val mode: String,
            val mirror_enabled: Boolean,
            val running: Boolean,
            val connected: Boolean,
            val last_scan: String?,
            val bot_start: String?,
            val health: String?,
            val balance: Int?,
            val peak_balance: Int?,
            val drawdown_pct: Float?,
            val open_positions: Int?,
            val total_trades: Int?,
            val paused: Boolean?,
            val halt_reason: String?
        )
    }
}

package com.aiscanner.app.data.api

import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST

interface ApiService {

    @GET("/api/health")
    suspend fun health(): HealthResponse

    @GET("/api/bot/status")
    suspend fun botStatus(): BotStatus

    @GET("/api/dashboard")
    suspend fun dashboard(): DashboardResponse

    @GET("/api/signals")
    suspend fun signals(): List<Signal>

    @GET("/api/trades")
    suspend fun trades(): TradesResponse

    @GET("/api/market-analysis")
    suspend fun marketAnalysis(): MarketAnalysis

    @GET("/api/risk/status")
    suspend fun riskStatus(): RiskStatus

    @POST("/api/bot/pause")
    suspend fun pause(@Header("X-API-Key") key: String): ControlResult

    @POST("/api/bot/resume")
    suspend fun resume(@Header("X-API-Key") key: String): ControlResult

    @POST("/api/bot/emergency-stop")
    suspend fun emergencyStop(@Header("X-API-Key") key: String): ControlResult
}

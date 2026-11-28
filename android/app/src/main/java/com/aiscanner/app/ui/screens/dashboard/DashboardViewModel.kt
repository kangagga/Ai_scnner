package com.aiscanner.app.ui.screens.dashboard

import android.app.Application
import androidx.lifecycle.viewModelScope
import com.aiscanner.app.data.api.ApiService
import com.aiscanner.app.data.api.BotStatus
import com.aiscanner.app.data.api.DashboardResponse
import com.aiscanner.app.data.api.Portfolio
import com.aiscanner.app.data.api.Signal
import com.aiscanner.app.data.api.SignalSummary
import com.aiscanner.app.data.repository.ApiResult
import com.aiscanner.app.ui.screens.BaseViewModel
import com.aiscanner.app.ui.screens.UiState
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class DashboardViewModel(app: Application) : BaseViewModel(app) {
    private val _uiState = MutableStateFlow<UiState<DashboardResponse>>(UiState.Loading)
    val uiState: StateFlow<UiState<DashboardResponse>> = _uiState.asStateFlow()
    private val _isHealthy = MutableStateFlow(false)
    val isHealthy: StateFlow<Boolean> = _isHealthy.asStateFlow()
    private val _status = MutableStateFlow<ApiService.Status?>(null)
    val status: StateFlow<ApiService.Status?> = _status.asStateFlow()
    private val _signals = MutableStateFlow<List<Signal>>(emptyList())
    val signals: StateFlow<List<Signal>> = _signals.asStateFlow()

    // Data live scanner & aktivitas dari endpoint /api/status
    private val _scanProgress = MutableStateFlow<ApiService.ScanProgress?>(null)
    val scanProgress: StateFlow<ApiService.ScanProgress?> = _scanProgress.asStateFlow()
    private val _activityLogs = MutableStateFlow<List<ApiService.LogItem>>(emptyList())
    val activityLogs: StateFlow<List<ApiService.LogItem>> = _activityLogs.asStateFlow()
    private val _marketAnalysis = MutableStateFlow<com.aiscanner.app.data.api.MarketAnalysis?>(null)
    val marketAnalysis: StateFlow<com.aiscanner.app.data.api.MarketAnalysis?> = _marketAnalysis.asStateFlow()

    init { viewModelScope.launch { while (true) { fetch(); delay(10_000) } } }

    fun load() { viewModelScope.launch { _uiState.value = UiState.Loading; fetch() } }
    fun refreshData() = load()

    private suspend fun fetch() {
        val h = repository.getHealth()
        if (h is ApiResult.Error) {
            _isHealthy.value = false
            _uiState.value = UiState.Error(h.message, h.disconnected)
            return
        }
        _isHealthy.value = true

        val sigs = (repository.getSignals() as? ApiResult.Success)?.data ?: emptyList()
        _signals.value = sigs
        val st = (repository.getStatus() as? ApiResult.Success)?.data
        _status.value = st
        _scanProgress.value = st?.scan_progress
        _activityLogs.value = st?.logs.orEmpty()
        _marketAnalysis.value = (repository.getMarketAnalysis() as? ApiResult.Success)?.data
        val risk = (repository.getRiskStatus() as? ApiResult.Success)?.data

        val bot = BotStatus(
            mode = "PAPER", running = true, connected = true,
            lastScan = st?.last_scan, botStart = st?.bot_start,
            health = risk?.health, balance = risk?.balance, peakBalance = risk?.peakBalance,
            drawdownPct = risk?.drawdownPct, openPositions = risk?.openPositions,
            totalTrades = risk?.totalTrades, paused = risk?.tradingHalted,
            haltReason = risk?.haltReason
        )
        val portfolio = risk?.let {
            Portfolio(
                balance = it.balance, peakBalance = it.peakBalance, drawdownPct = it.drawdownPct,
                dailyPnl = it.dailyPnl, dailyPnlPct = it.dailyPnlPct, portfolioHeat = it.portfolioHeat,
                consecutiveLoss = it.consecutiveLoss, tradingHalted = it.tradingHalted,
                openPositions = it.openPositions, maxPositions = it.maxPositions,
                totalTrades = it.totalTrades
            )
        }
        val summary = SignalSummary(
            total = sigs.size,
            buy = sigs.count { it.signal?.contains("BUY") == true },
            sell = sigs.count { it.signal?.contains("SELL") == true },
            avgWr = null,
            avgScore = sigs.mapNotNull { it.confidence }.takeIf { it.isNotEmpty() }?.average()
        )
        _uiState.value = UiState.Success(
            DashboardResponse(bot = bot, portfolio = portfolio, performance = null, signals = summary)
        )
    }
}

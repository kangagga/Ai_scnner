package com.aiscanner.app.ui.screens.learning

import android.app.Application
import androidx.lifecycle.viewModelScope
import com.aiscanner.app.data.api.DashboardResponse
import com.aiscanner.app.data.api.Trade
import com.aiscanner.app.data.repository.ApiResult
import com.aiscanner.app.ui.screens.BaseViewModel
import com.aiscanner.app.ui.screens.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class LearningViewModel(app: Application) : BaseViewModel(app) {

    data class SetupPerf(
        val strategy: String,
        val count: Int,
        val wins: Int,
        val winRate: Double
    )

    data class LearningData(
        val overall: DashboardResponse?,
        val setups: List<SetupPerf>,
        val totalLosses: Int,
        val avgLossPct: Double,
        val bestSetup: SetupPerf?
    )

    private val _uiState = MutableStateFlow<UiState<LearningData>>(UiState.Loading)
    val uiState: StateFlow<UiState<LearningData>> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _uiState.value = UiState.Loading

            val dashResult = repository.getDashboard()
            val tradesResult = repository.getTrades()

            val dash = (dashResult as? ApiResult.Success)?.data
            val trades = (tradesResult as? ApiResult.Success)?.data?.trades.orEmpty()

            val bothDisconnected =
                (dashResult is ApiResult.Error && dashResult.disconnected) &&
                (tradesResult is ApiResult.Error && tradesResult.disconnected)

            if (bothDisconnected) {
                val err = dashResult as ApiResult.Error
                _uiState.value = UiState.Error(err.message, disconnected = true)
                return@launch
            }

            val grouped = trades.groupBy { it.strategy ?: it.signal ?: "Lainnya" }
            val setups = grouped.map { (key, list) ->
                val wins = list.count { it.result?.equals("WIN", ignoreCase = true) == true }
                SetupPerf(
                    strategy = key,
                    count = list.size,
                    wins = wins,
                    winRate = if (list.isNotEmpty()) wins * 100.0 / list.size else 0.0
                )
            }.sortedByDescending { it.winRate }

            val losses = trades.filter { it.result?.equals("LOSS", ignoreCase = true) == true }
            val avgLoss = if (losses.isNotEmpty()) losses.mapNotNull { it.pnlPct }.average() else 0.0

            _uiState.value = UiState.Success(
                LearningData(
                    overall = dash,
                    setups = setups,
                    totalLosses = losses.size,
                    avgLossPct = avgLoss,
                    bestSetup = setups.maxByOrNull { it.winRate }
                )
            )
        }
    }
}

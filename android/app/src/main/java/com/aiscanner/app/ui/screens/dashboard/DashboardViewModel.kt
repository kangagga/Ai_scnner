package com.aiscanner.app.ui.screens.dashboard

import android.app.Application
import androidx.lifecycle.viewModelScope
import com.aiscanner.app.data.api.ApiService
import com.aiscanner.app.data.api.Signal
import com.aiscanner.app.data.repository.ApiResult
import com.aiscanner.app.ui.screens.BaseViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class DashboardViewModel(app: Application) : BaseViewModel(app) {
    private val _isHealthy = MutableStateFlow(false)
    val isHealthy: StateFlow<Boolean> = _isHealthy.asStateFlow()
    private val _status = MutableStateFlow<ApiService.Status?>(null)
    val status: StateFlow<ApiService.Status?> = _status.asStateFlow()
    private val _signals = MutableStateFlow<List<Signal>>(emptyList())
    val signals: StateFlow<List<Signal>> = _signals.asStateFlow()
    private val _scanProgress = MutableStateFlow<Map<String, Int>>(emptyMap())
    val scanProgress: StateFlow<Map<String, Int>> = _scanProgress.asStateFlow()
    private val _isLoading = MutableStateFlow(true)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    init {
        viewModelScope.launch { while (true) { fetch(); delay(10_000) } }
    }

    fun refreshData() { viewModelScope.launch { fetch() } }

    private suspend fun fetch() {
        _isLoading.value = true
        val h = repository.getHealth()
        _isHealthy.value = h is ApiResult.Success && h.data.ok == true
        if (h is ApiResult.Error) { _error.value = h.message; _isLoading.value = false; return }
        _error.value = null

        val sg = repository.getSignals()
        if (sg is ApiResult.Success) _signals.value = sg.data

        val st = repository.getStatus()
        if (st is ApiResult.Success) {
            var s = st.data
            val sigs = _signals.value
            // Statistik status backend kosong (0): hitung dari sinyal terbaru.
            if ((s.stats?.total ?: 0) == 0 && sigs.isNotEmpty()) {
                s = s.copy(stats = ApiService.Stats(
                    total = sigs.size,
                    buy = sigs.count { it.signal?.contains("BUY") == true },
                    sell = sigs.count { it.signal?.contains("SELL") == true },
                    avg_wr = null, // backend tidak mengisi win rate
                    avg_score = sigs.mapNotNull { it.confidence }.average().toFloat()
                ))
            }
            _status.value = s
            _scanProgress.value = mapOf(
                "done" to (s.scan_progress?.done ?: 0),
                "total" to (s.scan_progress?.total ?: 1)
            )
        }
        _isLoading.value = false
    }
}

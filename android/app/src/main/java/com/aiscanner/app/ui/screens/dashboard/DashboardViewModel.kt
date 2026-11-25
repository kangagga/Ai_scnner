package com.aiscanner.app.ui.screens.dashboard

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.aiscanner.app.data.model.Signal
import com.aiscanner.app.data.repository.SignalRepository
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.collectAsStateAsFlow
import kotlinx.coroutines.launch
import java.util.*

class DashboardViewModel(repository: SignalRepository = SignalRepository()) : ViewModel() {

    private val _isHealthy = MutableStateFlow(false)
    val isHealthy: Flow<Boolean> = _isHealthy.asFlow()

    private val _status = MutableStateFlow<ApiService.Status?>(null)
    val status: Flow<ApiService.Status?> = _status.asFlow()

    private val _signals = MutableStateFlow<List<Signal>>(emptyList())
    val signals: Flow<List<Signal>> = _signals.asFlow()

    private val _scanProgress = MutableStateFlow<Map<String, Int>>("0:0")
    val scanProgress: Flow<Map<String, Int>> = _scanProgress.asFlow()

    initScope {
        viewModelScope.launch {
            _isHealthy.value = repository.isHealthy()
        }
        viewModelScope.launch {
            val statusFlow = repository.observeStatus()
            collectAsStateAsFlow(_status).value
        }
        viewModelScope.launch {
            val signalsFlow = repository.observeSignals()
            collectAsStateAsFlow(_signals).value
        }
    }

    fun refreshData() {
        viewModelScope.launch {
            _signals.value = repository.getSignals()
            val s = repository.getStatus()
            if (s != null) {
                _status.value = s
                _scanProgress.value = mapOf(
                    "done" to (s.scan_progress?.done ?: 0),
                    "total" to (s.scan_progress?.total ?: 1)
                )
            }
        }
    }
}

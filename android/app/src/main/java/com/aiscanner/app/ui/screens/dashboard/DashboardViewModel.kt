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
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class DashboardViewModel(repository: SignalRepository = SignalRepository()) : ViewModel() {

    private val _isHealthy = MutableStateFlow(false)
    val isHealthy: StateFlow<Boolean> = _isHealthy.asStateFlow()

    private val _status = MutableStateFlow<ApiService.Status?>(null)
    val status: StateFlow<ApiService.Status?> = _status.asStateFlow()

    private val _signals = MutableStateFlow<List<Signal>>(emptyList())
    val signals: StateFlow<List<Signal>> = _signals.asStateFlow()

    private val _scanProgress = MutableStateFlow<Map<String, Int>>(emptyMap())
    val scanProgress: StateFlow<Map<String, Int>> = _scanProgress.asStateFlow()

    init {
        viewModelScope.launch {
            _isHealthy.value = repository.isHealthy()
        }
        viewModelScope.launch {
            repository.observeStatus().collect { _status.value = it }
        }
        viewModelScope.launch {
            repository.observeSignals().collect { _signals.value = it }
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

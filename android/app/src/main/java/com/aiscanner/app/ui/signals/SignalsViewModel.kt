package com.aiscanner.app.ui.signals

import android.app.Application
import androidx.lifecycle.viewModelScope
import com.aiscanner.app.data.api.Signal
import com.aiscanner.app.data.repository.SignalRepository
import com.aiscanner.app.ui.screens.BaseViewModel
import com.aiscanner.app.ui.screens.UiState
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SignalsViewModel(app: Application) : BaseViewModel(app) {

    private val _uiState = MutableStateFlow<UiState<List<Signal>>>(UiState.Loading)
    val uiState: StateFlow<UiState<List<Signal>>> = _uiState.asStateFlow()

    private val _filter = MutableStateFlow("Active")
    val filter: StateFlow<String> = _filter.asStateFlow()

    private val _signalRepository = SignalRepository()

    init {
        load()
    }

    fun setFilter(f: String) {
        _filter.value = f
    }

    fun load() {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            try {
                val signals = _signalRepository.getSignals()
                if (signals.isEmpty()) {
                    _uiState.value = UiState.Empty("Belum ada sinyal dari scanner")
                } else {
                    _uiState.value = UiState.Success(signals)
                }
            } catch (e: Exception) {
                _uiState.value = UiState.Error("Gagal memuat sinyal: ${e.message ?: "unknown error"}", disconnected = true)
            }
        }
    }
}
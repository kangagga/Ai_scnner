package com.aiscanner.app.ui.screens.risk

import android.app.Application
import androidx.lifecycle.viewModelScope
import com.aiscanner.app.data.api.RiskStatus
import com.aiscanner.app.data.repository.ApiResult
import com.aiscanner.app.ui.screens.BaseViewModel
import com.aiscanner.app.ui.screens.UiState
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Read-only (paper trading). Kontrol bot dinonaktifkan; stub dipertahankan agar layar tetap kompilasi. */
class RiskViewModel(app: Application) : BaseViewModel(app) {
    companion object { const val DEFAULT_CONTROL_KEY = "" }

    private val _uiState = MutableStateFlow<UiState<RiskStatus>>(UiState.Loading)
    val uiState: StateFlow<UiState<RiskStatus>> = _uiState.asStateFlow()
    private val _controlKey = MutableStateFlow(DEFAULT_CONTROL_KEY)
    val controlKey: StateFlow<String> = _controlKey.asStateFlow()
    private val _actionState = MutableStateFlow<String?>(null)
    val actionState: StateFlow<String?> = _actionState.asStateFlow()

    init { viewModelScope.launch { while (true) { fetch(); delay(10_000) } } }

    fun setControlKey(key: String) { _controlKey.value = key }
    fun load() { viewModelScope.launch { _uiState.value = UiState.Loading; fetch() } }
    fun pause() = disabled()
    fun resume() = disabled()
    fun emergencyStop() = disabled()
    private fun disabled() { _actionState.value = "error:Kontrol bot dinonaktifkan (aplikasi hanya baca)" }

    private suspend fun fetch() {
        _uiState.value = when (val r = repository.getRiskStatus()) {
            is ApiResult.Success -> UiState.Success(r.data)
            is ApiResult.Error -> UiState.Error(r.message, r.disconnected)
            ApiResult.Loading -> UiState.Loading
        }
    }
}

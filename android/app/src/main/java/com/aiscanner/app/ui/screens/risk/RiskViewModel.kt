package com.aiscanner.app.ui.screens.risk

import android.app.Application
import androidx.lifecycle.viewModelScope
import com.aiscanner.app.data.api.ControlResult
import com.aiscanner.app.data.api.RiskStatus
import com.aiscanner.app.data.repository.ApiResult
import com.aiscanner.app.ui.screens.BaseViewModel
import com.aiscanner.app.ui.screens.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class RiskViewModel(app: Application) : BaseViewModel(app) {

    companion object {
        // API Control Key TIDAK ditanam di APK. Pengguna harus memasukkan
        // key yang sama dengan konfigurasi server (env AI_SCANNER_API_KEY).
        const val DEFAULT_CONTROL_KEY = ""
    }

    private val _uiState = MutableStateFlow<UiState<RiskStatus>>(UiState.Loading)
    val uiState: StateFlow<UiState<RiskStatus>> = _uiState.asStateFlow()

    private val _controlKey = MutableStateFlow(DEFAULT_CONTROL_KEY)
    val controlKey: StateFlow<String> = _controlKey.asStateFlow()

    private val _actionState = MutableStateFlow<String?>(null)
    val actionState: StateFlow<String?> = _actionState.asStateFlow()

    init {
        load()
    }

    fun setControlKey(key: String) {
        _controlKey.value = key
    }

    fun load() {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            _uiState.value = when (val r = repository.getRiskStatus()) {
                is ApiResult.Success -> UiState.Success(r.data)
                is ApiResult.Error -> UiState.Error(r.message, r.disconnected)
                ApiResult.Loading -> UiState.Loading
            }
        }
    }

    fun pause() = runControlAction { repository.pauseBot(_controlKey.value) }

    fun resume() = runControlAction { repository.resumeBot(_controlKey.value) }

    fun emergencyStop() = runControlAction { repository.emergencyStop(_controlKey.value) }

    private fun runControlAction(block: suspend () -> ApiResult<ControlResult>) {
        viewModelScope.launch {
            _actionState.value = "running"
            when (val r = block()) {
                is ApiResult.Success -> {
                    _actionState.value = if (r.data.ok == true) {
                        "ok:" + (r.data.action ?: "")
                    } else {
                        "error:" + (r.data.error ?: "Perintah ditolak server")
                    }
                    load()
                }
                is ApiResult.Error -> _actionState.value = "error:" + r.message
                ApiResult.Loading -> Unit
            }
        }
    }
}

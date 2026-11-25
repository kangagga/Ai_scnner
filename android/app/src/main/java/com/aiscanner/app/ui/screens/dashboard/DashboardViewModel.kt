package com.aiscanner.app.ui.screens.dashboard

import android.app.Application
import androidx.lifecycle.viewModelScope
import com.aiscanner.app.data.api.DashboardResponse
import com.aiscanner.app.data.repository.ApiResult
import com.aiscanner.app.ui.screens.BaseViewModel
import com.aiscanner.app.ui.screens.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class DashboardViewModel(app: Application) : BaseViewModel(app) {

    private val _uiState = MutableStateFlow<UiState<DashboardResponse>>(UiState.Loading)
    val uiState: StateFlow<UiState<DashboardResponse>> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            _uiState.value = when (val r = repository.getDashboard()) {
                is ApiResult.Success -> UiState.Success(r.data)
                is ApiResult.Error -> UiState.Error(r.message, r.disconnected)
                ApiResult.Loading -> UiState.Loading
            }
        }
    }
}

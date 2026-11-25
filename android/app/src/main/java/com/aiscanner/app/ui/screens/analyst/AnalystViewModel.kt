package com.aiscanner.app.ui.screens.analyst

import android.app.Application
import androidx.lifecycle.viewModelScope
import com.aiscanner.app.data.api.MarketAnalysis
import com.aiscanner.app.data.repository.ApiResult
import com.aiscanner.app.ui.screens.BaseViewModel
import com.aiscanner.app.ui.screens.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class AnalystViewModel(app: Application) : BaseViewModel(app) {

    private val _uiState = MutableStateFlow<UiState<MarketAnalysis>>(UiState.Loading)
    val uiState: StateFlow<UiState<MarketAnalysis>> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            _uiState.value = when (val r = repository.getMarketAnalysis()) {
                is ApiResult.Success -> UiState.Success(r.data)
                is ApiResult.Error -> UiState.Error(r.message, r.disconnected)
                ApiResult.Loading -> UiState.Loading
            }
        }
    }
}

package com.aiscanner.app.ui.screens.signals

import android.app.Application
import androidx.lifecycle.viewModelScope
import com.aiscanner.app.data.api.Signal
import com.aiscanner.app.data.repository.ApiResult
import com.aiscanner.app.ui.screens.BaseViewModel
import com.aiscanner.app.ui.screens.UiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SignalsViewModel(app: Application) : BaseViewModel(app) {

    private val _uiState = MutableStateFlow<UiState<List<Signal>>>(UiState.Loading)
    val uiState: StateFlow<UiState<List<Signal>>> = _uiState.asStateFlow()

    private val _filter = MutableStateFlow("Active")
    val filter: StateFlow<String> = _filter.asStateFlow()

    init {
        load()
    }

    fun setFilter(f: String) {
        _filter.value = f
    }

    fun load() {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            _uiState.value = when (val r = repository.getSignals()) {
                is ApiResult.Success -> UiState.Success(r.data)
                is ApiResult.Error -> UiState.Error(r.message, r.disconnected)
                ApiResult.Loading -> UiState.Loading
            }
        }
    }
}

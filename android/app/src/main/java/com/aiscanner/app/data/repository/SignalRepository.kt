package com.aiscanner.app.data.repository

import com.aiscanner.app.data.model.Signal
import com.aiscanner.app.data.api.ApiService
import com.aiscanner.app.data.api.RetrofitClient
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import retrofit2.Response

class SignalRepository {
    private val apiService: ApiService = RetrofitClient.apiService

    /** Health check */
    suspend fun isHealthy(): Boolean {
        try {
            val resp = apiService.health()
            return resp.ok
        } catch (e: Exception) {
            return false
        }
    }

    /** Status lengkap */
    suspend fun getStatus(): ApiService.Status? {
        try {
            return apiService.status()
        } catch (e: Exception) {
            return null
        }
    }

    /** Sinyal terbaru */
    suspend fun getSignals(): List<Signal> {
        try {
            return apiService.signals()
        } catch (e: Exception) {
            return emptyList()
        }
    }

    /** Flow untuk update real-time */
    fun observeStatus(): Flow<ApiService.Status?> = flow {
        while (true) {
            val status = getStatus()
            emit(status)
            delay(5000) // refresh setiap 5 detik
        }
    }

    /** Flow untuk update sinyal */
    fun observeSignals(): Flow<List<Signal>> = flow {
        while (true) {
            val signals = getSignals()
            emit(signals)
            delay(5000)
        }
    }
}
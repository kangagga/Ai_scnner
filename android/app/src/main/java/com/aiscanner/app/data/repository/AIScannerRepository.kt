package com.aiscanner.app.data.repository

import com.aiscanner.app.data.api.ApiService
import com.aiscanner.app.data.api.BotStatus
import com.aiscanner.app.data.api.ControlResult
import com.aiscanner.app.data.api.DashboardResponse
import com.aiscanner.app.data.api.MarketAnalysis
import com.aiscanner.app.data.api.RiskStatus
import com.aiscanner.app.data.api.Signal
import com.aiscanner.app.data.api.TradesResponse
import com.aiscanner.app.data.local.SignalDao
import com.aiscanner.app.data.local.toEntity
import com.aiscanner.app.data.local.toSignal
import java.io.IOException
import retrofit2.HttpException

sealed class ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>()
    data class Error(val message: String, val disconnected: Boolean = false) : ApiResult<Nothing>()
    object Loading : ApiResult<Nothing>()
}

class AIScannerRepository(
    private val apiProvider: () -> ApiService,
    private val signalDao: SignalDao
) {

    private fun <T> safeCall(block: suspend (ApiService) -> T): ApiResult<T> {
        return try {
            ApiResult.Success(block(apiProvider()))
        } catch (e: IOException) {
            ApiResult.Error("Tidak terhubung ke server bot", disconnected = true)
        } catch (e: HttpException) {
            ApiResult.Error("Server error ${e.code()}")
        } catch (e: Exception) {
            ApiResult.Error(e.message ?: "Error tidak diketahui")
        }
    }

    suspend fun getDashboard(): ApiResult<DashboardResponse> = safeCall { it.dashboard() }

    suspend fun getBotStatus(): ApiResult<BotStatus> = safeCall { it.botStatus() }

    suspend fun getSignals(): ApiResult<List<Signal>> {
        return try {
            val remote = apiProvider().signals()
            runCatching {
                signalDao.clear()
                signalDao.insertAll(remote.map { it.toEntity() })
            }
            ApiResult.Success(remote)
        } catch (e: IOException) {
            val cached = runCatching { signalDao.getAll() }.getOrNull()
            if (!cached.isNullOrEmpty()) {
                ApiResult.Success(cached.map { it.toSignal() })
            } else {
                ApiResult.Error("Tidak terhubung ke server bot", disconnected = true)
            }
        } catch (e: HttpException) {
            ApiResult.Error("Server error ${e.code()}")
        } catch (e: Exception) {
            ApiResult.Error(e.message ?: "Error tidak diketahui")
        }
    }

    suspend fun getTrades(): ApiResult<TradesResponse> = safeCall { it.trades() }

    suspend fun getMarketAnalysis(): ApiResult<MarketAnalysis> = safeCall { it.marketAnalysis() }

    suspend fun getRiskStatus(): ApiResult<RiskStatus> = safeCall { it.riskStatus() }

    suspend fun pauseBot(key: String): ApiResult<ControlResult> = safeCall { it.pause(key) }

    suspend fun resumeBot(key: String): ApiResult<ControlResult> = safeCall { it.resume(key) }

    suspend fun emergencyStop(key: String): ApiResult<ControlResult> = safeCall { it.emergencyStop(key) }
}

package com.aiscanner.app.data.repository

import com.aiscanner.app.data.api.ApiService
import com.aiscanner.app.data.api.BotStatus
import com.aiscanner.app.data.api.DashboardResponse
import com.aiscanner.app.data.api.MarketAnalysis
import com.aiscanner.app.data.api.RiskStatus
import com.aiscanner.app.data.api.Signal
import com.aiscanner.app.data.api.TradesResponse
import com.aiscanner.app.data.local.SignalDao
import java.io.IOException
import retrofit2.HttpException

sealed class ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>()
    data class Error(val message: String, val disconnected: Boolean = false) : ApiResult<Nothing>()
    object Loading : ApiResult<Nothing>()
}

class AIScannerRepository(
    private val apiProvider: () -> ApiService,
    @Suppress("unused") private val signalDao: SignalDao
) {
    private suspend fun <T> safeCall(block: suspend (ApiService) -> T): ApiResult<T> = try {
        ApiResult.Success(block(apiProvider()))
    } catch (e: IOException) {
        ApiResult.Error("Tidak terhubung ke server bot", disconnected = true)
    } catch (e: HttpException) {
        ApiResult.Error("Server error ${e.code()}")
    } catch (e: Exception) {
        ApiResult.Error(e.message ?: "Error tidak diketahui")
    }

    suspend fun getHealth() = safeCall { it.health() }
    suspend fun getStatus() = safeCall { it.status() }
    suspend fun getRiskStatus(): ApiResult<RiskStatus> = safeCall { it.portfolio() }
    suspend fun getMarketAnalysis(): ApiResult<MarketAnalysis> = safeCall { it.marketRegime() }

    /** Terbaru di atas. Gagal = Error (bukan list kosong), tanpa data cache palsu. */
    suspend fun getSignals(): ApiResult<List<Signal>> =
        when (val r = safeCall { it.signals() }) {
            is ApiResult.Success -> ApiResult.Success(r.data.sortedByDescending { it.timestamp ?: "" })
            is ApiResult.Error -> r
            ApiResult.Loading -> ApiResult.Loading
        }

    // Belum ada endpoint backend untuk ini: jujur "tidak tersedia".
    suspend fun getTrades(): ApiResult<TradesResponse> =
        ApiResult.Error("Journal belum tersedia di backend")
    suspend fun getDashboard(): ApiResult<DashboardResponse> =
        ApiResult.Error("Endpoint dashboard tidak tersedia")
    suspend fun getBotStatus(): ApiResult<BotStatus> =
        ApiResult.Error("Endpoint bot status tidak tersedia")
}

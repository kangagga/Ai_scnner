package com.aiscanner.app.data.api

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Konfigurasi jaringan.
 *
 * Base URL dapat dikonfigurasi per perangkat lewat layar Settings
 * (ikon gerigi di pojok kanan atas). Default menunjuk ke emulator Android
 * (10.0.2.2 = host). Untuk perangkat fisik, setel ke IP LAN mesin bot,
 * misal "http://192.168.1.10:5000/".
 */
object NetworkModule {

    const val DEFAULT_BASE_URL = "http://10.0.2.2:5000/"

    @Volatile
    var baseUrl: String = DEFAULT_BASE_URL

    private val lock = Any()

    @Volatile
    private var retrofitInstance: Retrofit? = null

    @Volatile
    private var apiInstance: ApiService? = null

    private val loggingInterceptor by lazy {
        HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }
    }

    private val okHttpClient by lazy {
        OkHttpClient.Builder()
            .addInterceptor(loggingInterceptor)
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(25, TimeUnit.SECONDS)
            .writeTimeout(15, TimeUnit.SECONDS)
            .build()
    }

    private fun buildRetrofit(): Retrofit =
        Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()

    /** Mengambil instance ApiService saat ini (di-build ulang jika base URL berubah). */
    fun getApi(): ApiService {
        apiInstance?.let { return it }
        synchronized(lock) {
            apiInstance?.let { return it }
            val api = buildRetrofit().create(ApiService::class.java)
            retrofitInstance = null
            apiInstance = api
            return api
        }
    }

    /** Mengganti base URL dan memaksa Retrofit di-build ulang pada pemanggilan berikutnya. */
    fun updateBaseUrl(newUrl: String) {
        val normalized = if (newUrl.endsWith("/")) newUrl else "$newUrl/"
        synchronized(lock) {
            baseUrl = normalized
            retrofitInstance = null
            apiInstance = null
        }
    }
}

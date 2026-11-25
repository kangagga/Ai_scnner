package com.aiscanner.app

import android.app.Application
import android.content.Context
import com.aiscanner.app.data.api.NetworkModule
import com.aiscanner.app.data.local.AppDatabase
import com.aiscanner.app.data.repository.AIScannerRepository

class AIScannerApp : Application() {

    val database by lazy { AppDatabase.getInstance(this) }

    val repository by lazy {
        AIScannerRepository({ NetworkModule.getApi() }, database.signalDao())
    }

    override fun onCreate() {
        super.onCreate()
        // Muat base URL tersimpan (jika ada) sebelum network dipakai.
        val prefs = getSharedPreferences("ai_scanner_prefs", Context.MODE_PRIVATE)
        val saved = prefs.getString("base_url", null)
        if (!saved.isNullOrBlank()) {
            NetworkModule.updateBaseUrl(saved)
        }
    }

    fun saveBaseUrl(url: String) {
        NetworkModule.updateBaseUrl(url)
        getSharedPreferences("ai_scanner_prefs", Context.MODE_PRIVATE)
            .edit()
            .putString("base_url", url)
            .apply()
    }
}

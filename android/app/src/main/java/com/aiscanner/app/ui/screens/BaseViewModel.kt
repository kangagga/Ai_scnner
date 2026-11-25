package com.aiscanner.app.ui.screens

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import com.aiscanner.app.AIScannerApp
import com.aiscanner.app.data.repository.AIScannerRepository

abstract class BaseViewModel(app: Application) : AndroidViewModel(app) {
    protected val repository: AIScannerRepository
        get() = (getApplication<AIScannerApp>()).repository
}

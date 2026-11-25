package com.aiscanner.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.aiscanner.app.ui.navigation.AppNavigation
import com.aiscanner.app.ui.theme.AIScannerTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AIScannerTheme {
                AppNavigation()
            }
        }
    }
}

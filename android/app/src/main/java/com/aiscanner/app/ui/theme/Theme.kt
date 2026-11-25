package com.aiscanner.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val DarkColorScheme = darkColorScheme(
    primary = GreenPrimary,
    onPrimary = NavyBackground,
    primaryContainer = NavyCardElevated,
    onPrimaryContainer = TextPrimary,
    secondary = BluePrimary,
    onSecondary = NavyBackground,
    tertiary = PurplePrimary,
    onTertiary = TextPrimary,
    background = NavyBackground,
    onBackground = TextPrimary,
    surface = NavySurface,
    onSurface = TextPrimary,
    surfaceVariant = NavySurfaceVariant,
    onSurfaceVariant = TextSecondary,
    outline = OutlineDark,
    error = RedLoss,
    onError = NavyBackground
)

@Composable
fun AIScannerTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColorScheme,
        typography = AppTypography,
        content = content
    )
}

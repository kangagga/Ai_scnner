package com.aiscanner.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val DarkColorScheme = darkColorScheme(
    primary = ElectricBlue,
    onPrimary = MidnightNavy,
    primaryContainer = NavyCardElevated,
    onPrimaryContainer = TextPrimary,
    secondary = NeonCyan,
    onSecondary = MidnightNavy,
    tertiary = PurplePrimary,
    onTertiary = TextPrimary,
    background = MidnightNavy,
    onBackground = TextPrimary,
    surface = DarkNavy,
    onSurface = TextPrimary,
    surfaceVariant = NavySurfaceVariant,
    onSurfaceVariant = TextSecondary,
    outline = OutlineDark,
    error = RedLoss,
    onError = MidnightNavy
)

@Composable
fun AIScannerTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColorScheme,
        typography = AppTypography,
        content = content
    )
}

package com.aiscanner.app.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material.icons.filled.SignalCellularAlt
import androidx.compose.ui.graphics.vector.ImageVector

enum class BottomNavItem(
    val route: String,
    val label: String,
    val icon: ImageVector
) {
    Dashboard("dashboard", "Dashboard", Icons.Filled.Dashboard),
    Analyst("analyst", "Analyst", Icons.Filled.Insights),
    Signals("signals", "Signals", Icons.Filled.SignalCellularAlt),
    Journal("journal", "Journal", Icons.Filled.MenuBook),
    Risk("risk", "Risk", Icons.Filled.Shield),
    Learning("learning", "Learning", Icons.Filled.Psychology)
}

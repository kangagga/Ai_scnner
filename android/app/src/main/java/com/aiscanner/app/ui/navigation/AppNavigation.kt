package com.aiscanner.app.ui.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.aiscanner.app.ui.screens.analyst.AnalystScreen
import com.aiscanner.app.ui.screens.analyst.AnalystViewModel
import com.aiscanner.app.ui.screens.dashboard.DashboardScreen
import com.aiscanner.app.ui.screens.dashboard.DashboardViewModel
import com.aiscanner.app.ui.screens.journal.JournalScreen
import com.aiscanner.app.ui.screens.journal.JournalViewModel
import com.aiscanner.app.ui.screens.learning.LearningScreen
import com.aiscanner.app.ui.screens.learning.LearningViewModel
import com.aiscanner.app.ui.screens.risk.RiskScreen
import com.aiscanner.app.ui.screens.risk.RiskViewModel
import com.aiscanner.app.ui.screens.settings.SettingsScreen
import com.aiscanner.app.ui.screens.signals.SignalsScreen
import com.aiscanner.app.ui.screens.signals.SignalsViewModel
import com.aiscanner.app.ui.theme.ElectricBlue
import com.aiscanner.app.ui.theme.NavyCardElevated
import com.aiscanner.app.ui.theme.NavySurface
import com.aiscanner.app.ui.theme.TextPrimary
import com.aiscanner.app.ui.theme.TextSecondary

private const val ROUTE_SETTINGS = "settings"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppNavigation() {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination
    val showBottomBar = currentDestination?.route != ROUTE_SETTINGS

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "AI SCANNER",
                        color = TextPrimary,
                        fontSize = 18.sp
                    )
                },
                actions = {
                    IconButton(onClick = { navController.navigate(ROUTE_SETTINGS) }) {
                        Icon(
                            imageVector = Icons.Filled.Settings,
                            contentDescription = "Pengaturan",
                            tint = TextSecondary
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = NavySurface
                )
            )
        },
        bottomBar = {
            if (showBottomBar) {
                NavigationBar(containerColor = NavySurface) {
                    BottomNavItem.entries.forEach { item ->
                        val selected = currentDestination?.route == item.route
                        NavigationBarItem(
                            selected = selected,
                            onClick = {
                                navController.navigate(item.route) {
                                    popUpTo(navController.graph.findStartDestination().id) {
                                        saveState = true
                                    }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(item.icon, contentDescription = item.label) },
                            label = { Text(item.label, fontSize = 10.sp) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = ElectricBlue,
                                selectedTextColor = ElectricBlue,
                                unselectedIconColor = TextSecondary,
                                unselectedTextColor = TextSecondary,
                                indicatorColor = NavyCardElevated
                            )
                        )
                    }
                }
            }
        }
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = BottomNavItem.Dashboard.route,
            modifier = Modifier.padding(padding)
        ) {
            composable(BottomNavItem.Dashboard.route) {
                val vm: DashboardViewModel = viewModel()
                DashboardScreen(vm)
            }
            composable(BottomNavItem.Analyst.route) {
                val vm: AnalystViewModel = viewModel()
                AnalystScreen(vm)
            }
            composable(BottomNavItem.Signals.route) {
                val vm: SignalsViewModel = viewModel()
                SignalsScreen(vm)
            }
            composable(BottomNavItem.Journal.route) {
                val vm: JournalViewModel = viewModel()
                JournalScreen(vm)
            }
            composable(BottomNavItem.Risk.route) {
                val vm: RiskViewModel = viewModel()
                RiskScreen(vm)
            }
            composable(BottomNavItem.Learning.route) {
                val vm: LearningViewModel = viewModel()
                LearningScreen(vm)
            }
            composable(ROUTE_SETTINGS) {
                SettingsScreen()
            }
        }
    }
}

package com.wealthvault.app

import android.graphics.Color
import android.os.Bundle
import androidx.activity.SystemBarStyle
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccountBalanceWallet
import androidx.compose.material.icons.outlined.GridView
import androidx.compose.material.icons.outlined.Link
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.wealthvault.app.ui.AppViewModel
import com.wealthvault.app.ui.BrokersScreen
import com.wealthvault.app.ui.HoldingsScreen
import com.wealthvault.app.ui.OverviewScreen
import com.wealthvault.app.ui.SettingsScreen
import com.wealthvault.app.ui.SignInScreen
import com.wealthvault.app.ui.WealthVaultTheme
import com.wealthvault.app.ui.Wv

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val TABS = listOf(
    Tab("overview", "Overview", Icons.Outlined.GridView),
    Tab("holdings", "Holdings", Icons.Outlined.AccountBalanceWallet),
    Tab("brokers", "Brokers", Icons.Outlined.Link),
    Tab("settings", "Settings", Icons.Outlined.Settings),
)

class MainActivity : ComponentActivity() {
    private val vm: AppViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Debug builds only: tests start the app signed in with
        // `adb shell am start -n com.vangala.wealthvault/com.wealthvault.app.MainActivity --es wv_base <url> --es wv_token <jwt>`
        if (BuildConfig.DEBUG) {
            val base = intent.getStringExtra("wv_base")
            val token = intent.getStringExtra("wv_token")
            if (base != null && token != null) vm.debugSignIn(base, token)
        }
        setContent {
            val session by vm.session.collectAsState()
            val theme = session?.theme ?: "system"
            val dark = theme == "dark" || (theme == "system" && isSystemInDarkTheme())
            // status bar and gesture bar icons follow the app's theme, not just the phone's
            LaunchedEffect(dark) {
                val bars = if (dark) SystemBarStyle.dark(Color.TRANSPARENT) else SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT)
                enableEdgeToEdge(statusBarStyle = bars, navigationBarStyle = bars)
            }
            WealthVaultTheme(theme) {
                when {
                    session == null -> Unit // reading the saved session
                    session?.token == null -> SignInScreen(vm)
                    else -> SignedIn(vm)
                }
            }
        }
    }
}

@Composable
private fun SignedIn(vm: AppViewModel) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    LaunchedEffect(Unit) { vm.refreshAll() }
    Scaffold(
        containerColor = Wv.c.bg,
        bottomBar = {
            NavigationBar(containerColor = Wv.c.surface) {
                TABS.forEach { tab ->
                    NavigationBarItem(
                        selected = entry?.destination?.route == tab.route,
                        onClick = {
                            nav.navigate(tab.route) {
                                popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = null) },
                        label = { Text(tab.label) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = Wv.c.accent,
                            selectedTextColor = Wv.c.accent,
                            indicatorColor = Wv.c.accentWeak,
                            unselectedIconColor = Wv.c.text3,
                            unselectedTextColor = Wv.c.text3,
                        ),
                    )
                }
            }
        },
    ) { inner ->
        NavHost(nav, startDestination = "overview", modifier = Modifier.fillMaxSize().background(Wv.c.bg).padding(inner)) {
            composable("overview") { OverviewScreen(vm) }
            composable("holdings") { HoldingsScreen(vm) }
            composable("brokers") { BrokersScreen(vm) }
            composable("settings") { SettingsScreen(vm) }
        }
    }
}

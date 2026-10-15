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
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.outlined.TrendingUp
import androidx.compose.material.icons.outlined.CandlestickChart
import androidx.compose.material.icons.outlined.MoreHoriz
import androidx.compose.material.icons.outlined.Radar
import androidx.compose.material.icons.outlined.ShowChart
import android.net.Uri
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.ui.Alignment
import androidx.compose.ui.unit.dp
import androidx.navigation.navArgument
import com.wealthvault.app.ui.AnalysisViewModel
import com.wealthvault.app.ui.MomentumScreen
import com.wealthvault.app.ui.PageTitle
import com.wealthvault.app.ui.SignalsScreen
import com.wealthvault.app.ui.Stage2Screen
import com.wealthvault.app.ui.StrategyScreen
import com.wealthvault.app.ui.WvCard
import com.wealthvault.app.ui.pagePad
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

private data class Tab(val route: String, val label: String, val icon: ImageVector, val sub: String = "")

private val TABS = listOf(
    Tab("overview", "Overview", Icons.Outlined.GridView),
    Tab("holdings", "Holdings", Icons.Outlined.AccountBalanceWallet),
    Tab("signals", "Signals", Icons.Outlined.Radar),
    Tab("stage2", "Stage 2", Icons.AutoMirrored.Outlined.TrendingUp),
    Tab("more", "More", Icons.Outlined.MoreHoriz),
)

/** The pages under More, in the web app's order. */
private val MORE = listOf(
    Tab("momentum", "Momentum", Icons.Outlined.ShowChart, "Trend, returns and strength of any stock"),
    Tab("strategy", "Strategies", Icons.Outlined.CandlestickChart, "Swing V2.1 and the ATH breakout, with backtests"),
    Tab("brokers", "Brokers", Icons.Outlined.Link, "Sync, log in, add or remove a broker"),
    Tab("settings", "Settings", Icons.Outlined.Settings, "Theme and account"),
)

class MainActivity : ComponentActivity() {
    private val vm: AppViewModel by viewModels()
    private val avm: AnalysisViewModel by viewModels()

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
                    else -> SignedIn(vm, avm)
                }
            }
        }
    }
}

@Composable
private fun SignedIn(vm: AppViewModel, avm: AnalysisViewModel) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route?.substringBefore('?')
    val tabOf = { r: String? -> if (MORE.any { it.route == r }) "more" else r }
    val openStock = { kind: String, symbol: String -> nav.navigate("$kind?symbol=${Uri.encode(symbol)}") }
    LaunchedEffect(Unit) { vm.refreshAll() }
    Scaffold(
        containerColor = Wv.c.bg,
        bottomBar = {
            NavigationBar(containerColor = Wv.c.surface) {
                TABS.forEach { tab ->
                    NavigationBarItem(
                        selected = tabOf(route) == tab.route,
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
            composable("overview") { OverviewScreen(vm, avm) { nav.navigate("signals") { popUpTo(nav.graph.findStartDestination().id) { saveState = true }; launchSingleTop = true; restoreState = true } } }
            composable("holdings") { HoldingsScreen(vm) { openStock("momentum", it) } }
            composable("signals") { SignalsScreen(vm, avm) { openStock("momentum", it) } }
            composable("stage2") { Stage2Screen(avm) { openStock("momentum", it) } }
            composable("more") { MoreScreen { nav.navigate(it) } }
            composable("momentum?symbol={symbol}", arguments = listOf(navArgument("symbol") { nullable = true; defaultValue = null })) { e ->
                MomentumScreen(vm, avm, e.arguments?.getString("symbol")) { openStock("strategy", it) }
            }
            composable("strategy?symbol={symbol}", arguments = listOf(navArgument("symbol") { nullable = true; defaultValue = null })) { e ->
                StrategyScreen(vm, avm, e.arguments?.getString("symbol"))
            }
            composable("brokers") { BrokersScreen(vm, avm) }
            composable("settings") { SettingsScreen(vm) }
        }
    }
}

@Composable
private fun MoreScreen(onOpen: (String) -> Unit) {
    LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { PageTitle("More", "Analysis tools, brokers and settings") }
        items(MORE) { t ->
            WvCard(Modifier.clickable { onOpen(t.route) }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(t.icon, contentDescription = null, tint = Wv.c.accent)
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text(t.label, style = Wv.title, color = Wv.c.text)
                        Text(t.sub, style = Wv.small, color = Wv.c.text3)
                    }
                    Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null, tint = Wv.c.text3)
                }
            }
        }
    }
}

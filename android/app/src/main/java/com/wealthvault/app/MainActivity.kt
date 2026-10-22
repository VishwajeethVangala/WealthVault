package com.wealthvault.app

import android.graphics.Color
import android.os.Bundle
import androidx.activity.SystemBarStyle
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.fragment.app.FragmentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccountBalanceWallet
import androidx.compose.material.icons.outlined.GridView
import androidx.compose.material.icons.outlined.Link
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.outlined.StarOutline
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.foundation.layout.Box
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
import com.wealthvault.app.ui.LockScreen
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
    Tab("more", "More", Icons.Outlined.MoreHoriz),
)

/** The pages under More, in the web app's order. */
private val MORE = listOf(
    Tab("momentum", "Momentum", Icons.Outlined.ShowChart, "Trend, returns and strength of any stock"),
    Tab("strategy", "Strategies", Icons.Outlined.CandlestickChart, "Swing V2.1 and the ATH breakout, with backtests"),
    Tab("brokers", "Brokers", Icons.Outlined.Link, "Sync, log in, add or remove a broker"),
    Tab("settings", "Settings", Icons.Outlined.Settings, "Theme, hide amounts, app lock and account"),
    Tab("feedback", "Send feedback", Icons.Outlined.ChatBubbleOutline, "An idea, a problem, or praise"),
    Tab("rate", "Rate WealthVault", Icons.Outlined.StarOutline, "On Google Play"),
)

class MainActivity : FragmentActivity() {
    private val vm: AppViewModel by viewModels()
    private val avm: AnalysisViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // count the opening (not a screen rotation), for the review prompt
        if (savedInstanceState == null) lifecycleScope.launch { vm.prefs.countOpen() }
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
            // the eye switch: hide every rupee amount, as the phone remembers it
            LaunchedEffect(session?.hideAmounts) { com.wealthvault.app.ui.Privacy.hidden = session?.hideAmounts != false }
            val unlocked by vm.unlocked.collectAsState()
            val lockOn = session?.lock == true && session?.token != null
            // with the lock on, hide the screen from screenshots and the recent-apps thumbnail
            LaunchedEffect(lockOn) {
                if (lockOn) window.addFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
                else window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
            }
            WealthVaultTheme(theme) {
                when {
                    session == null -> Unit // reading the saved session
                    session?.token == null -> SignInScreen(vm)
                    lockOn && !unlocked -> LockScreen { vm.unlocked.value = true }
                    else -> SignedIn(vm, avm)
                }
            }
        }
    }

    // Leaving the app (home, another app, screen off) locks it again; turning the phone over does not.
    override fun onStop() {
        super.onStop()
        if (!isChangingConfigurations) vm.unlocked.value = false
    }
}

@Composable
private fun SignedIn(vm: AppViewModel, avm: AnalysisViewModel) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route?.substringBefore('?')
    val tabOf = { r: String? -> if (MORE.any { it.route == r }) "more" else r }
    val openStock = { kind: String, symbol: String -> nav.navigate("$kind?symbol=${Uri.encode(symbol)}") }
    val goTab = { route: String ->
        nav.navigate(route) {
            popUpTo(nav.graph.findStartDestination().id) { saveState = true }
            launchSingleTop = true
            restoreState = true
        }
    }
    LaunchedEffect(Unit) { vm.refreshAll() }
    val context = androidx.compose.ui.platform.LocalContext.current
    // after a few openings, ask (once in a while) for a Play Store review; Google decides whether it shows
    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(20_000)
        (context as? android.app.Activity)?.let { com.wealthvault.app.ui.maybeAskForReview(it, vm) }
    }
    Scaffold(
        containerColor = Wv.c.bg,
        bottomBar = {
            NavigationBar(containerColor = Wv.c.surface) {
                TABS.forEach { tab ->
                    NavigationBarItem(
                        selected = tabOf(route) == tab.route,
                        onClick = {
                            // More again while inside it: back to its list
                            if (tab.route == "more" && tabOf(route) == "more") {
                                nav.popBackStack("more", inclusive = false)
                                return@NavigationBarItem
                            }
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
            composable("overview") {
                OverviewScreen(
                    vm, avm,
                    onSignals = { preset -> avm.signalsPreset.value = preset; goTab("signals") },
                    onHoldings = { goTab("holdings") },
                    onBrokers = { nav.navigate("brokers") },
                    onStock = { openStock("momentum", it) },
                )
            }
            composable("holdings") { HoldingsScreen(vm) { openStock("momentum", it) } }
            composable("signals") { SignalsScreen(vm, avm) { openStock("momentum", it) } }
            composable("more") { MoreScreen { route -> if (route == "rate") com.wealthvault.app.ui.openPlayListing(context) else nav.navigate(route) } }
            composable("momentum?symbol={symbol}", arguments = listOf(navArgument("symbol") { nullable = true; defaultValue = null })) { e ->
                SubPage({ nav.popBackStack() }) { MomentumScreen(vm, avm, e.arguments?.getString("symbol")) { openStock("strategy", it) } }
            }
            composable("strategy?symbol={symbol}", arguments = listOf(navArgument("symbol") { nullable = true; defaultValue = null })) { e ->
                SubPage({ nav.popBackStack() }) { StrategyScreen(vm, avm, e.arguments?.getString("symbol")) }
            }
            composable("brokers") { SubPage({ nav.popBackStack() }) { BrokersScreen(vm, avm) } }
            composable("settings") { SubPage({ nav.popBackStack() }) { SettingsScreen(vm) } }
            composable("feedback") { SubPage({ nav.popBackStack() }) { com.wealthvault.app.ui.FeedbackScreen(vm) } }
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

/** A page reached from another one: a back row above it. */
@Composable
private fun SubPage(onBack: () -> Unit, content: @Composable () -> Unit) {
    Column(Modifier.fillMaxSize()) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.clickable(onClick = onBack).padding(start = 8.dp, end = 16.dp, top = 8.dp, bottom = 0.dp),
        ) {
            Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = Wv.c.text2, modifier = Modifier.padding(8.dp))
            Text("Back", style = Wv.sub, color = Wv.c.text2)
        }
        Box(Modifier.weight(1f)) { content() }
    }
}

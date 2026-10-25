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
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.automirrored.outlined.ShowChart
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import com.wealthvault.app.ui.needsAttention
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
import androidx.compose.material.icons.outlined.Radar
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
import androidx.compose.ui.unit.sp
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

/** The five places you move between all day. Brokers, settings and feedback sit behind the profile menu. */
private val TABS = listOf(
    Tab("overview", "Overview", Icons.Outlined.GridView),
    Tab("holdings", "Holdings", Icons.Outlined.AccountBalanceWallet),
    Tab("signals", "Signals", Icons.Outlined.Radar),
    Tab("momentum", "Momentum", Icons.AutoMirrored.Outlined.ShowChart),
    Tab("strategy", "Strategy", Icons.Outlined.CandlestickChart),
)

/** Pages opened from the profile menu (they sit over a tab, with a Back row). */
private val SUB_PAGES = setOf("brokers", "settings", "feedback")

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
    val onSubPage = route in SUB_PAGES
    // the pages inside the navigation graph are built once, so they must read the current page when a tap happens,
    // not the page that was showing when they were built
    val liveRoute = rememberUpdatedState(route)
    val context = androidx.compose.ui.platform.LocalContext.current
    val brokers by vm.brokers.collectAsState()
    val attention = brokers.data.orEmpty().any { needsAttention(it) }

    // moves to a tab; each tab keeps its place (scroll, search) while you are elsewhere
    val goTab = { target: String ->
        nav.navigate(target) {
            popUpTo(nav.graph.findStartDestination().id) { saveState = true }
            launchSingleTop = true
            restoreState = true
        }
    }
    // the tabs you came from, so Back from a stock returns to the page it was opened from
    val origins = remember { mutableStateListOf<String>() }
    val openStock = { kind: String, symbol: String ->
        val here = liveRoute.value
        avm.requestStock(kind, symbol)
        here?.takeIf { r -> TABS.any { it.route == r } && r != kind }?.let { origins.add(it) }
        if (here in SUB_PAGES) nav.popBackStack()
        goTab(kind)
    }
    val openSub = { target: String ->
        if (liveRoute.value in SUB_PAGES) nav.popBackStack()
        nav.navigate(target) { launchSingleTop = true }
        Unit
    }
    LaunchedEffect(Unit) { vm.refreshAll() }
    // after a few openings, ask (once in a while) for a Play Store review; Google decides whether it shows
    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(20_000)
        (context as? android.app.Activity)?.let { com.wealthvault.app.ui.maybeAskForReview(it, vm) }
    }
    Scaffold(
        containerColor = Wv.c.bg,
        topBar = {
            TopBar(
                vm, attention,
                onBrokers = { openSub("brokers") },
                onSettings = { openSub("settings") },
                onFeedback = { openSub("feedback") },
                onRate = { com.wealthvault.app.ui.openPlayListing(context) },
            )
        },
        bottomBar = {
            // five tabs share the width, so their labels do not grow with large system text (they would be cut off)
            val density = androidx.compose.ui.platform.LocalDensity.current
            androidx.compose.runtime.CompositionLocalProvider(
                androidx.compose.ui.platform.LocalDensity provides androidx.compose.ui.unit.Density(density.density, fontScale = minOf(density.fontScale, 1.0f)),
            ) {
            NavigationBar(containerColor = Wv.c.surface) {
                TABS.forEach { tab ->
                    NavigationBarItem(
                        selected = route == tab.route,
                        onClick = {
                            origins.clear()
                            // leave Brokers, Settings or Feedback first, so the tab opens as you left it
                            if (onSubPage) nav.popBackStack()
                            goTab(tab.route)
                        },
                        icon = { Icon(tab.icon, contentDescription = null) },
                        label = { Text(tab.label, maxLines = 1, softWrap = false, fontSize = if (androidx.compose.ui.platform.LocalConfiguration.current.screenWidthDp < 380) 10.sp else 11.sp) },
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
            }
        },
    ) { inner ->
        NavHost(nav, startDestination = "overview", modifier = Modifier.fillMaxSize().background(Wv.c.bg).padding(inner)) {
            composable("overview") {
                OverviewScreen(
                    vm, avm,
                    onSignals = { preset -> avm.signalsPreset.value = preset; goTab("signals") },
                    onHoldings = { goTab("holdings") },
                    onBrokers = { openSub("brokers") },
                    onStock = { openStock("momentum", it) },
                )
            }
            composable("holdings") { HoldingsScreen(vm) { openStock("momentum", it) } }
            composable("signals") { SignalsScreen(vm, avm) { openStock("momentum", it) } }
            composable("momentum") {
                val request by avm.stockRequest.collectAsState()
                MomentumScreen(vm, avm, request) { openStock("strategy", it) }
            }
            composable("strategy") {
                val request by avm.stockRequest.collectAsState()
                StrategyScreen(vm, avm, request)
            }
            composable("brokers") { SubPage({ nav.popBackStack() }) { BrokersScreen(vm, avm) } }
            composable("settings") { SubPage({ nav.popBackStack() }) { SettingsScreen(vm) } }
            composable("feedback") { SubPage({ nav.popBackStack() }) { com.wealthvault.app.ui.FeedbackScreen(vm) } }
        }
        // after the NavHost on purpose: the last Back handler registered is the first asked, and the NavHost has its own
        androidx.activity.compose.BackHandler(enabled = origins.isNotEmpty() && (route == "momentum" || route == "strategy")) {
            goTab(origins.removeAt(origins.lastIndex))
        }
    }
}

/** The strip above every page: the app name, the eye switch for amounts, and the profile menu. */
@Composable
private fun TopBar(vm: AppViewModel, attention: Boolean, onBrokers: () -> Unit, onSettings: () -> Unit, onFeedback: () -> Unit, onRate: () -> Unit) {
    val session by vm.session.collectAsState()
    var open by remember { mutableStateOf(false) }
    val who = session?.name?.ifBlank { null } ?: session?.email.orEmpty()
    val initial = who.trim().take(1).uppercase().ifBlank { "W" }
    val pick = { action: () -> Unit -> open = false; action() }
    Row(
        Modifier.fillMaxWidth().background(Wv.c.bg).windowInsetsPadding(WindowInsets.statusBars).padding(start = 16.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("WealthVault", style = Wv.title, color = Wv.c.text, modifier = Modifier.weight(1f))
        com.wealthvault.app.ui.EyeButton(vm)
        Box {
            IconButton(onClick = { open = true }) {
                Box(Modifier.size(34.dp).clip(CircleShape).background(Wv.c.accentWeak), contentAlignment = Alignment.Center) {
                    Text(initial, style = Wv.title, color = Wv.c.accent)
                }
            }
            if (attention) Box(Modifier.align(Alignment.TopEnd).padding(top = 10.dp, end = 10.dp).size(10.dp).clip(CircleShape).background(Wv.c.loss))
            DropdownMenu(expanded = open, onDismissRequest = { open = false }, containerColor = Wv.c.surface) {
                Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                    Text(session?.name?.ifBlank { null } ?: "Signed in", style = Wv.sub.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                    session?.email?.takeIf { it.isNotBlank() }?.let { Text(it, style = Wv.small, color = Wv.c.text3) }
                }
                HorizontalDivider(color = Wv.c.border)
                MenuRow("Brokers", Icons.Outlined.Link, if (attention) "A broker needs a login" else null) { pick(onBrokers) }
                MenuRow("Settings", Icons.Outlined.Settings) { pick(onSettings) }
                MenuRow("Send feedback", Icons.Outlined.ChatBubbleOutline) { pick(onFeedback) }
                MenuRow("Rate WealthVault", Icons.Outlined.StarOutline) { pick(onRate) }
            }
        }
    }
}

@Composable
private fun MenuRow(label: String, icon: ImageVector, note: String? = null, onClick: () -> Unit) {
    DropdownMenuItem(
        text = {
            Column {
                Text(label, style = Wv.body, color = Wv.c.text)
                note?.let { Text(it, style = Wv.small, color = Wv.c.loss) }
            }
        },
        leadingIcon = { Icon(icon, contentDescription = null, tint = Wv.c.accent) },
        onClick = onClick,
    )
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

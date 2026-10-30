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
import androidx.compose.material.icons.outlined.Share
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
import com.wealthvault.app.ui.LockSetupScreen
import com.wealthvault.app.ui.NotificationsPromptScreen
import com.wealthvault.app.push.Notifier
import com.wealthvault.app.push.PushRegistration
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
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
        com.wealthvault.app.ui.Analytics.attach(applicationContext)
        Notifier.ensureChannels(applicationContext)
        rememberTappedNotification(intent)
        // count the opening (not a screen rotation), for the review prompt
        if (savedInstanceState == null) lifecycleScope.launch { vm.prefs.countOpen() }
        // Debug builds only: tests start the app signed in with
        // `adb shell am start -n com.vangala.wealthvault/com.wealthvault.app.MainActivity --es wv_base <url> --es wv_token <jwt>`
        if (BuildConfig.DEBUG) {
            val base = intent.getStringExtra("wv_base")
            val token = intent.getStringExtra("wv_token")
            // `--ez wv_ask true` also shows the analytics consent screen
            // `--ez wv_real true` signs in as an ordinary (non-demo) account, so the required app lock setup shows
            // `--es wv_fake_push ath_h` shows a sample notification of that kind, with no push and no server
            intent.getStringExtra("wv_fake_push")?.let { kind ->
                val note = com.wealthvault.app.data.PushNote(
                    kind = kind, title = "Strategy calls · your holdings",
                    body = "RELIANCE: entry signal on today's live price. A strategy signal, not advice.",
                    body_masked = "RELIANCE: entry signal on today's live price. A strategy signal, not advice.",
                    public_title = "Strategy calls update", route = "strategy:NSE:RELIANCE",
                    extra = debugExtra(kind),
                )
                Notifier.show(applicationContext, kind, "debug-$kind", note, hideAmounts = false)
            }
            if (base != null && token != null) vm.debugSignIn(base, token, demoAccount = !intent.getBooleanExtra("wv_real", false), askAnalytics = intent.getBooleanExtra("wv_ask", false))
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
            // the home screen widget follows the eye switch, the app lock and signing in or out
            LaunchedEffect(session?.hideAmounts, session?.lock, session?.token) { if (session != null) com.wealthvault.app.widget.NetWorthWidget.requestUpdate(applicationContext) }
            // usage analytics and crash reports follow the person's choice (off until they allow it)
            LaunchedEffect(session?.analytics) { if (session != null) com.wealthvault.app.ui.Analytics.apply(session?.analytics == "granted") }
            LaunchedEffect(session?.token, session?.userId) { com.wealthvault.app.ui.Analytics.identify(if (session?.token != null) session?.userId else null) }
            // whether the phone lets us show notifications; looked at again each time the app comes back to the front
            var notificationsOn by remember { mutableStateOf(NotificationManagerCompat.from(this@MainActivity).areNotificationsEnabled()) }
            LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { notificationsOn = NotificationManagerCompat.from(this@MainActivity).areNotificationsEnabled() }
            // a phone that allows notifications tells the server it belongs to this person (and stops when signed out)
            LaunchedEffect(session?.token, notificationsOn) { if (session?.token != null && notificationsOn) PushRegistration.registerCurrent(applicationContext) }
            val unlocked by vm.unlocked.collectAsState()
            val lockSetupSkipped by vm.lockSetupSkipped.collectAsState()
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
                    // app lock is required: a signed-in person who has not turned it on is asked to, before anything else
                    session?.lock != true && session?.demo != true && !lockSetupSkipped -> LockSetupScreen(vm)
                    session?.analytics == null -> com.wealthvault.app.ui.AnalyticsConsentScreen(vm)
                    // Android 13+ asks permission to show notifications; asked once, never nagged
                    android.os.Build.VERSION.SDK_INT >= 33 && !notificationsOn && session?.notifAsked != true -> NotificationsPromptScreen(vm)
                    else -> SignedIn(vm, avm)
                }
            }
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        rememberTappedNotification(intent)
    }

    /** Debug builds only: the extras a sample notification of this kind would carry. */
    private fun debugExtra(kind: String): String = when (kind) {
        "networth_weekly" -> """{"tone":"up","series":[100,99.5,100.2,101.1,100.6,101.8,102.4],"actions":[{"label":"Overview","route":"overview"},{"label":"Holdings","route":"holdings"}]}"""
        "networth_daily", "us_digest" -> """{"tone":"down","actions":[{"label":"Holdings","route":"holdings"},{"label":"Overview","route":"overview"}]}"""
        "kite_login" -> """{"tone":"flat","actions":[{"label":"Log in to Kite","route":"brokers"}]}"""
        else -> """{"tone":"up","actions":[{"label":"Open strategy","route":"strategy:NSE:RELIANCE"},{"label":"Holdings","route":"holdings"}]}"""
    }

    /** A tapped notification says which page to open; the signed-in screen picks it up once it is showing. */
    private fun rememberTappedNotification(intent: android.content.Intent?) {
        val page = intent?.getStringExtra(Notifier.EXTRA_OPEN) ?: return
        vm.pendingOpen.value = page to (intent.getStringExtra(Notifier.EXTRA_KIND) ?: "")
        intent.removeExtra(Notifier.EXTRA_OPEN)
    }

    // Leaving the app (home, another app, screen off) locks it again; turning the phone over does not.
    override fun onStop() {
        super.onStop()
        if (!isChangingConfigurations) vm.unlocked.value = false
        com.wealthvault.app.widget.NetWorthWidget.requestUpdate(applicationContext) // the widget shows what the app last saw
    }
}

@Composable
private fun SignedIn(vm: AppViewModel, avm: AnalysisViewModel) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route?.substringBefore('?')
    val onSubPage = route in SUB_PAGES
    val analyticsChoice = vm.session.collectAsState().value?.analytics
    LaunchedEffect(route, analyticsChoice) { com.wealthvault.app.ui.Analytics.screen(route) }
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
    // a tapped notification opens the page it is about
    val tapped by vm.pendingOpen.collectAsState()
    LaunchedEffect(tapped) {
        tapped?.let { (page, kind) ->
            // 'strategy:NSE:RELIANCE' opens the Strategy tab on that stock; a plain page name just opens the page
            val target = page.substringBefore(':')
            val stock = page.substringAfter(':', "")
            if (stock.isNotBlank() && (target == "strategy" || target == "momentum")) avm.requestStock(target, stock)
            if (target in SUB_PAGES) nav.navigate(target) else if (TABS.any { it.route == target }) goTab(target)
            com.wealthvault.app.ui.Analytics.log("notification_opened", "kind" to kind)
            vm.pendingOpen.value = null
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
          Column {
            TopBar(
                vm, attention,
                onBrokers = { openSub("brokers") },
                onSettings = { openSub("settings") },
                onFeedback = { openSub("feedback") },
                onRate = { com.wealthvault.app.ui.openPlayListing(context) },
            )
            com.wealthvault.app.ui.UpdateBanner()
          }
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
                val shareContext = androidx.compose.ui.platform.LocalContext.current
                MenuRow("Share WealthVault", Icons.Outlined.Share) { pick { com.wealthvault.app.ui.ShareApp.open(shareContext, "menu") } }
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

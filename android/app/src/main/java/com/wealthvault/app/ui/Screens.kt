package com.wealthvault.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.wealthvault.app.BuildConfig
import com.wealthvault.app.data.ASSET_CLASS_LABEL
import com.wealthvault.app.data.BrokerSession
import com.wealthvault.app.data.Holding

val pagePad = PaddingValues(horizontal = 16.dp, vertical = 12.dp)

@Composable
fun PageTitle(title: String, sub: String) {
    Column(Modifier.padding(bottom = 4.dp)) {
        Text(title, style = Wv.h1, color = Wv.c.text)
        Text(sub, style = Wv.sub, color = Wv.c.text3)
    }
}

@Composable
fun PrimaryButton(text: String, busy: Boolean = false, enabled: Boolean = true, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = enabled && !busy,
        shape = RoundedCornerShape(10.dp),
        colors = ButtonDefaults.buttonColors(containerColor = Wv.c.accent, contentColor = Wv.c.onAccent),
        modifier = modifier,
    ) {
        if (busy) {
            CircularProgressIndicator(Modifier.size(16.dp), color = Wv.c.onAccent, strokeWidth = 2.dp)
            Spacer(Modifier.width(8.dp))
        }
        Text(text)
    }
}

// --- sign in -------------------------------------------------------------------------------------------

@Composable
fun SignInScreen(vm: AppViewModel) {
    val session by vm.session.collectAsState()
    val busy by vm.signingIn.collectAsState()
    val message by vm.message.collectAsState()
    val context = LocalContext.current
    var url by remember(session?.baseUrl) { mutableStateOf(session?.baseUrl ?: "") }

    Column(
        Modifier.fillMaxSize().background(Wv.c.bg).padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Box(Modifier.size(48.dp).clip(RoundedCornerShape(12.dp)).background(Wv.c.text), contentAlignment = Alignment.Center) {
            Text("W", color = Wv.c.bg, style = Wv.title)
        }
        Spacer(Modifier.height(20.dp))
        Text("WealthVault", style = Wv.h1, color = Wv.c.text)
        Text("All your broker accounts in one place.", style = Wv.sub, color = Wv.c.text3)
        Spacer(Modifier.height(28.dp))
        // the address is built in (wvBaseUrl); the field only shows for a build without one
        val askForUrl = BuildConfig.DEFAULT_BASE_URL.isBlank()
        if (askForUrl) {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                label = { Text("Server address") },
                placeholder = { Text("https://your-app.azurewebsites.net") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Text("The same address you open WealthVault at in the browser.", style = Wv.small, color = Wv.c.text3, modifier = Modifier.padding(top = 4.dp))
            Spacer(Modifier.height(20.dp))
        }
        PrimaryButton("Sign in with Google", busy = busy, enabled = url.startsWith("http"), modifier = Modifier.fillMaxWidth()) {
            if (askForUrl) vm.saveBaseUrl(url)
            vm.signIn(context)
        }
        if (message != null) {
            Spacer(Modifier.height(16.dp))
            Note(message!!, bad = true)
        }
    }
}

// --- overview ------------------------------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OverviewScreen(vm: AppViewModel, avm: AnalysisViewModel, onSignals: () -> Unit = {}) {
    val signals by avm.signals.collectAsState()
    val liveSignals by avm.liveSignals.collectAsState()
    val history by avm.history.collectAsState()
    val targets by avm.targets.collectAsState()
    val risk by avm.risk.collectAsState()
    var editTargets by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { if (avm.history.value.data == null) avm.loadOverviewPanels() }
    val summary by vm.summary.collectAsState()
    val holdings by vm.holdings.collectAsState()
    // the signals summary needs the saved signals; read them once the portfolio itself is on screen
    val hasSummary = summary.data != null
    LaunchedEffect(hasSummary) { if (hasSummary && avm.signals.value.data == null && !avm.signals.value.loading) avm.loadSignals() }
    val syncing by vm.syncing.collectAsState()
    val message by vm.message.collectAsState()
    val s = summary.data?.snapshot

    PullToRefreshBox(isRefreshing = summary.loading, onRefresh = { vm.refreshAll(); avm.loadOverviewPanels() }) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f)) { PageTitle("Overview", if (s != null) "As of ${s.as_of_date}" else "Your whole portfolio") }
                    PrimaryButton(if (syncing == "all") "Syncing" else "Sync all", busy = syncing == "all") { vm.syncAll() }
                }
            }
            message?.let { item { Note(it) } }
            summary.error?.let { item { Note(it, bad = true) } }
            if (s == null && !summary.loading && summary.error == null) {
                item { Note("No snapshot yet. Connect a broker on the Brokers tab, then press Sync all.") }
            }
            if (s != null) {
                item {
                    Kpi("Portfolio value", compact(s.total_current_value), "Invested ${compact(s.total_invested_value)} · ${s.holdings_count} holdings")
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Kpi("Unrealised gain", signedMoney(s.total_unrealized_pnl), null, toneOf(s.total_unrealized_pnl), Modifier.weight(1f))
                        Kpi("Return", pct(s.total_pnl_percentage), null, toneOf(s.total_pnl_percentage), Modifier.weight(1f))
                    }
                }
                val dayPnl = holdings.data?.mapNotNull { it.day_pnl }?.takeIf { it.isNotEmpty() }?.sum()
                if (dayPnl != null) {
                    item { Kpi("Today", signedMoney(dayPnl), "Change across holdings with a live price", toneOf(dayPnl)) }
                }
                history.data?.let { h -> item { ValueCard(h) } }
                history.problem?.let { p -> item { Note("Value over time did not load: ${p.text}", bad = true) } }
                val mix = s.asset_allocation.mapValues { it.value.percentage_weight to it.value.absolute_value }
                item { AssetMixCard(mix, targets.data.orEmpty(), s.total_current_value) { editTargets = true } }
                // one line per company even when two brokers hold it
                val movers = holdings.data?.filter { it.day_change_percentage != null }?.distinctBy { displayName(it).uppercase() }?.sortedByDescending { it.day_change_percentage!! }
                if (!movers.isNullOrEmpty()) {
                    item { MoversCard(movers.take(3), movers.takeLast(3).reversed()) }
                }
                val sig = signals.data
                if (sig != null && avm.market.value == "in" && holdings.data != null) item { SignalsSummaryCard(holdings.data!!, sig, liveSignals, onSignals) }
                risk.data?.let { r -> item { RiskCard(r) } }
            }
        }
    }
    if (editTargets) TargetsEditor(vm, avm) { editTargets = false }
}

@Composable
private fun TargetsEditor(vm: AppViewModel, avm: AnalysisViewModel, onDone: () -> Unit) {
    val summary by vm.summary.collectAsState()
    val targets by avm.targets.collectAsState()
    val classes = (summary.data?.snapshot?.asset_allocation?.keys.orEmpty() + targets.data.orEmpty().keys).distinct()
    TargetsDialog(classes, targets.data.orEmpty(), onSave = { avm.saveTargets(it); onDone() }, onDismiss = onDone)
}

@Composable
private fun MoversCard(up: List<Holding>, down: List<Holding>) {
    WvCard {
        Label("Today's movers")
        (up + down.filter { d -> up.none { it.holding_id == d.holding_id } }).forEach { h ->
            Row(Modifier.padding(vertical = 3.dp)) {
                Text(displayName(h), style = Wv.body, color = Wv.c.text, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(pct(h.day_change_percentage), style = Wv.num, color = toneOf(h.day_change_percentage))
            }
        }
    }
}

/** "INDS02714 (Transformers & Rectifiers India Ltd)" reads as the company name; a bare ticker stays as is. */
fun displayName(h: Holding): String {
    val sym = h.instrument_symbol.substringAfter(':').trim()
    val name = Regex("""\((.+)\)\s*$""").find(sym)?.groupValues?.get(1)?.trim()
    return if (name.isNullOrBlank()) sym else name
}

/** The ticker part, shown small under the name when the name came from the brackets. */
private fun ticker(h: Holding): String? {
    val sym = h.instrument_symbol.substringAfter(':').trim()
    return if (sym.endsWith(")") && '(' in sym) sym.substringBefore('(').trim().takeIf { it.isNotBlank() && !it.startsWith("INDS") } else null
}

// --- holdings ------------------------------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HoldingsScreen(vm: AppViewModel, onStock: (String) -> Unit = {}) {
    val holdings by vm.holdings.collectAsState()
    var query by rememberSaveable { mutableStateOf("") }
    var cls by rememberSaveable { mutableStateOf<String?>(null) }
    var sort by rememberSaveable { mutableStateOf("value") }
    val all = holdings.data.orEmpty()
    val classes = all.map { it.asset_class }.distinct().sortedBy { ASSET_CLASS_LABEL.keys.indexOf(it) }
    val rows = all
        .filter { cls == null || it.asset_class == cls }
        .filter { query.isBlank() || it.instrument_symbol.contains(query.trim(), ignoreCase = true) || displayName(it).contains(query.trim(), ignoreCase = true) }
        .let { l ->
            when (sort) {
                "gain" -> l.sortedByDescending { it.pnlPct ?: -999.0 }
                "today" -> l.sortedByDescending { it.day_change_percentage ?: -999.0 }
                "name" -> l.sortedBy { displayName(it).lowercase() }
                else -> l.sortedByDescending { it.current_value }
            }
        }
    val shownValue = rows.sumOf { it.current_value }
    val shownGain = rows.sumOf { it.pnl ?: (it.current_value - it.invested) }

    PullToRefreshBox(isRefreshing = holdings.loading, onRefresh = { vm.refreshAll() }) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { PageTitle("Holdings", "${all.size} holdings · ${compact(all.sumOf { it.current_value })}") }
            item {
                OutlinedTextField(value = query, onValueChange = { query = it }, placeholder = { Text("Search a holding") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            }
            if (classes.size > 1) {
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
                        Chip("All", cls == null) { cls = null }
                        classes.forEach { c -> Chip(ASSET_CLASS_LABEL[c] ?: c, cls == c) { cls = c } }
                    }
                }
            }
            item {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Sort", style = Wv.small, color = Wv.c.text3)
                    listOf("value" to "Value", "gain" to "Gain %", "today" to "Today", "name" to "Name").forEach { (k, label) -> Chip(label, sort == k) { sort = k } }
                }
            }
            if (cls != null || query.isNotBlank()) {
                item {
                    Text("${rows.size} shown · ${compact(shownValue)} · ${signedMoney(shownGain)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(shownGain))
                }
            }
            holdings.error?.let { item { Note(it, bad = true) } }
            items(rows, key = { it.holding_id }) { h ->
                // stocks open their Momentum page; funds, gold and NPS have no price history there
                HoldingRow(h, if (h.asset_class == "EQUITY" && !tickerOf(h.instrument_symbol).startsWith("INDS")) ({ onStock(tickerOf(h.instrument_symbol)) }) else null)
            }
            if (rows.isEmpty() && !holdings.loading && holdings.error == null) item { Note(if (all.isEmpty()) "No holdings yet. Sync your brokers first." else "Nothing matches.") }
        }
    }
}

@Composable
fun Chip(text: String, on: Boolean, onClick: () -> Unit) {
    Text(
        text,
        style = Wv.small.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal),
        color = if (on) Wv.c.accent else Wv.c.text2,
        maxLines = 1,
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(if (on) Wv.c.accentWeak else Wv.c.surface2)
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 7.dp),
    )
}

@Composable
private fun HoldingRow(h: Holding, onOpen: (() -> Unit)?) {
    val us = h.currency.equals("USD", ignoreCase = true)
    WvCard(padding = 14, modifier = if (onOpen != null) Modifier.clickable(onClick = onOpen) else Modifier) {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Text(displayName(h), style = Wv.title, color = Wv.c.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(
                    "${listOfNotNull(ticker(h), ASSET_CLASS_LABEL[h.asset_class] ?: h.asset_class).distinct().joinToString(" · ")} · ${trimQty(h.quantity)} at ${if (us) "$" + String.format("%.2f", h.average_price) else price(h.average_price)}",
                    style = Wv.small,
                    color = Wv.c.text3,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(money(h.current_value), style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                Text("${signedMoney(h.pnl ?: (h.current_value - h.invested))} · ${pct(h.pnlPct, 1)}", style = Wv.small, color = toneOf(h.pnlPct))
                if (h.day_change_percentage != null) Text("today ${pct(h.day_change_percentage, 1)}", style = Wv.small, color = toneOf(h.day_change_percentage))
            }
        }
    }
}

fun trimQty(q: Double) = if (q % 1.0 == 0.0) q.toLong().toString() else String.format("%.3f", q).trimEnd('0').trimEnd('.')

// --- brokers -------------------------------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BrokersScreen(vm: AppViewModel, avm: AnalysisViewModel) {
    val brokers by vm.brokers.collectAsState()
    val syncing by vm.syncing.collectAsState()
    val catalog by avm.catalog.collectAsState()
    val problem by avm.brokerMessage.collectAsState()
    var dialog by remember { mutableStateOf<BrokerDialog?>(null) }
    LaunchedEffect(Unit) { avm.loadCatalog() }
    val itemFor = { b: BrokerSession -> catalog.data?.firstOrNull { it.broker_name.equals(b.broker_name, ignoreCase = true) } }

    PullToRefreshBox(isRefreshing = brokers.loading, onRefresh = { vm.loadBrokers(); avm.loadCatalog() }) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f)) { PageTitle("Brokers", "Your connections. Sync, log in, or add another broker.") }
                    PrimaryButton("Add") { avm.brokerMessage.value = null; dialog = BrokerDialog.Pick }
                }
            }
            brokers.error?.let { item { Note(it, bad = true) } }
            problem?.let { item { Note(it.text, bad = true) } }
            items(brokers.data.orEmpty(), key = { it.connection_id }) { b ->
                val item = itemFor(b)
                BrokerCard(
                    b, syncing,
                    onSync = { vm.syncOne(b.connection_id) },
                    onKeys = if (item != null && item.credential_fields.isNotEmpty()) ({ dialog = BrokerDialog.Keys(b, item) }) else null,
                    onRemove = { dialog = BrokerDialog.Remove(b) },
                )
            }
            if (brokers.data?.isEmpty() == true) item { Note("No broker connections yet. Press Add to connect your first broker.") }
        }
    }
    BrokerDialogs(dialog, avm, brokers.data.orEmpty(), onDialog = { dialog = it }, onChanged = { vm.refreshAll() })
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BrokerCard(b: BrokerSession, syncing: String?, onSync: () -> Unit, onKeys: (() -> Unit)?, onRemove: () -> Unit) {
    val context = LocalContext.current
    val (label, tone) = when (b.status) {
        "CONNECTED" -> "Connected" to Tone.Ok
        "SYNCING" -> "Syncing" to Tone.Info
        "AUTH_REQUIRED" -> "Login needed" to Tone.Warn
        "SESSION_EXPIRED" -> "Session expired" to Tone.Warn
        "DISCONNECTED" -> "Disconnected" to Tone.Off
        else -> "Problem" to Tone.Bad
    }
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(brokerName(b), style = Wv.title, color = Wv.c.text)
                Text(listOfNotNull(b.account_label, b.account_id.ifBlank { null }).joinToString(" · "), style = Wv.small, color = Wv.c.text3)
            }
            Badge(label, tone)
        }
        HorizontalDivider(color = Wv.c.border)
        Row {
            Column(Modifier.weight(1f)) {
                Text("Value", style = Wv.small, color = Wv.c.text3)
                Text(compact(b.total_valuation), style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
            }
            Column(Modifier.weight(1f)) {
                Text("Holdings", style = Wv.small, color = Wv.c.text3)
                Text("${b.holdings_count}", style = Wv.num, color = Wv.c.text)
            }
            Column(Modifier.weight(1.4f)) {
                Text("Last sync", style = Wv.small, color = Wv.c.text3)
                Text(localTime(b.last_sync_time), style = Wv.small, color = Wv.c.text2)
            }
        }
        b.error_message?.takeIf { it.isNotBlank() }?.let { Note(it, bad = true) }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = onSync, enabled = syncing == null, shape = RoundedCornerShape(10.dp)) {
                Text(if (syncing == b.connection_id) "Syncing…" else "Sync now", color = Wv.c.text)
            }
            if (!b.auth_url.isNullOrBlank() && b.status != "CONNECTED") {
                OutlinedButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(b.auth_url))) }, shape = RoundedCornerShape(10.dp)) {
                    Text("Log in", color = Wv.c.accent)
                }
            }
            if (onKeys != null) {
                OutlinedButton(onClick = onKeys, shape = RoundedCornerShape(10.dp)) { Text("Keys", color = Wv.c.text) }
            }
            TextButton(onClick = onRemove) { Text("Remove", color = Wv.c.loss) }
        }
    }
}

/** "Zerodha Kite Connect — Primary Account" without the account part, which is shown on the line below. */
fun brokerName(b: BrokerSession): String {
    val name = b.display_name.ifBlank { b.broker_name }
    val label = b.account_label
    return if (!label.isNullOrBlank()) name.removeSuffix(label).trimEnd(' ', '—', '-', '·') else name
}

/** The server sends UTC; show it in the phone's time zone, e.g. "14 Oct, 1:08 am". */
fun localTime(iso: String?): String {
    if (iso.isNullOrBlank()) return "Never"
    return try {
        java.time.OffsetDateTime.parse(iso).atZoneSameInstant(java.time.ZoneId.systemDefault())
            .format(java.time.format.DateTimeFormatter.ofPattern("d MMM, h:mm a"))
    } catch (e: Exception) {
        iso.take(16).replace('T', ' ')
    }
}

// --- settings ------------------------------------------------------------------------------------------

@Composable
fun SettingsScreen(vm: AppViewModel) {
    val session by vm.session.collectAsState()
    val s = session ?: return
    LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { PageTitle("Settings", "Signed in as ${s.name.ifBlank { s.email }}") }
        item {
            WvCard {
                Label("Theme")
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("system" to "Like the phone", "light" to "Light", "dark" to "Dark").forEach { (value, text) ->
                        Chip(text, s.theme == value) { vm.setTheme(value) }
                    }
                }
            }
        }
        item {
            WvCard {
                Label("Account")
                Text(s.email, style = Wv.body, color = Wv.c.text)
                Text("Server: ${s.baseUrl}", style = Wv.small, color = Wv.c.text3)
                Spacer(Modifier.height(4.dp))
                OutlinedButton(onClick = { vm.signOut() }, shape = RoundedCornerShape(10.dp)) { Text("Sign out", color = Wv.c.loss) }
            }
        }
        item { Text("Information from your brokers, not investment advice.", style = Wv.small, color = Wv.c.text3) }
        item { Text("WealthVault for Android ${com.wealthvault.app.BuildConfig.VERSION_NAME}", style = Wv.small, color = Wv.c.text3) }
    }
}

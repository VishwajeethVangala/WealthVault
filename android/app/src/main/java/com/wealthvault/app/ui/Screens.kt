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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
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
        // for store reviewers, who cannot use Google sign-in: one username and password for the sample account
        var demoOpen by remember { mutableStateOf(false) }
        var demoUser by remember { mutableStateOf("") }
        var demoPass by remember { mutableStateOf("") }
        TextButton(onClick = { demoOpen = true }, enabled = !busy && url.startsWith("http")) {
            Text("Sign in with a username", color = Wv.c.text2)
        }
        if (demoOpen) {
            androidx.compose.material3.AlertDialog(
                onDismissRequest = { demoOpen = false },
                containerColor = Wv.c.surface,
                title = { Text("Sign in with a username", color = Wv.c.text) },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(demoUser, { demoUser = it }, label = { Text("Username") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(
                            demoPass, { demoPass = it }, label = { Text("Password") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                            visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation(),
                        )
                    }
                },
                confirmButton = {
                    TextButton(enabled = demoUser.isNotBlank() && demoPass.isNotEmpty(), onClick = {
                        demoOpen = false
                        if (askForUrl) vm.saveBaseUrl(url)
                        vm.signInDemo(demoUser, demoPass)
                        demoPass = ""
                    }) { Text("Sign in", color = Wv.c.accent) }
                },
                dismissButton = { TextButton(onClick = { demoOpen = false }) { Text("Cancel", color = Wv.c.text2) } },
            )
        }
        val notice by vm.notice.collectAsState()
        notice?.let {
            Spacer(Modifier.height(16.dp))
            Note(it)
        }
        if (message != null) {
            Spacer(Modifier.height(16.dp))
            Note(message!!, bad = true)
        }
        val base = session?.baseUrl.orEmpty()
        if (base.startsWith("http")) {
            Spacer(Modifier.height(20.dp))
            androidx.compose.material3.TextButton(onClick = { openLink(context, "$base/privacy") }) {
                Text("Privacy policy", color = Wv.c.text2)
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
            // a little taller than the text: easier to hit with a thumb
            .padding(horizontal = 12.dp, vertical = 9.dp),
    )
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
    val syncMessage by vm.message.collectAsState()
    var dialog by remember { mutableStateOf<BrokerDialog?>(null) }
    val context = LocalContext.current
    LaunchedEffect(Unit) { avm.loadCatalog() }
    val itemFor = { b: BrokerSession -> catalog.data?.firstOrNull { it.broker_name.equals(b.broker_name, ignoreCase = true) } }
    val usesKeys = { b: BrokerSession -> (itemFor(b)?.credential_fields?.size ?: 0) > 0 }
    val list = brokers.data.orEmpty()
    // a login link, or the keys form for brokers that use API keys
    val reconnect = { b: BrokerSession ->
        val item = itemFor(b)
        when {
            item != null && item.credential_fields.isNotEmpty() -> dialog = BrokerDialog.Keys(b, item)
            !b.auth_url.isNullOrBlank() -> openLink(context, b.auth_url.orEmpty())
            else -> vm.syncOne(b.connection_id) // a sync asks the broker for a fresh login link
        }
    }

    PullToRefreshBox(isRefreshing = brokers.loading, onRefresh = { vm.loadBrokers(); avm.loadCatalog() }) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f)) { PageTitle("Brokers", "Read-only access. Nothing here can place orders or move money.") }
                    EyeButton(vm)
                    PrimaryButton("Add") { avm.brokerMessage.value = null; dialog = BrokerDialog.Pick }
                }
            }
            brokers.error?.let { item { Note(it, bad = true) } }
            problem?.let { item { Note(it.text, bad = true) } }
            syncMessage?.let { item { Note(it, bad = true) } }
            if (list.isNotEmpty()) {
                item {
                    val connected = list.count { it.status == "CONNECTED" }
                    val attention = list.count { needsLogin(it) }
                    val lastSync = list.mapNotNull { it.last_sync_time }.maxOrNull()
                    KpiGrid(
                        listOf(
                            Triple("Connected", "$connected / ${list.size}", if (attention > 0) "$attention needs attention" else "All healthy"),
                            Triple("Value synced", compact(list.sumOf { it.total_valuation }), "Holdings across all brokers"),
                            Triple("Positions", "${list.sumOf { it.holdings_count }}", "Before merging across brokers"),
                            Triple("Last sync", relativeTime(lastSync), lastSync?.let { localTime(it) } ?: "Run a sync to pull holdings"),
                        ),
                    )
                }
            }
            list.filter { needsLogin(it) }.forEach { b ->
                item(key = "attn-${b.connection_id}") {
                    WvCard {
                        Text(
                            "${brokerName(b)} ${if (b.status == "SESSION_EXPIRED") "session expired." else "needs a login."}",
                            style = Wv.sub.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.warn,
                        )
                        Text(
                            (if (b.holdings_count > 0) "Its ${b.holdings_count} holdings are shown from the last successful sync${b.last_sync_time?.let { " (${localTime(it)})" } ?: ""} and may be stale. " else "") +
                                (b.error_message?.takeIf { it.isNotBlank() } ?: if (usesKeys(b)) "Check your API credentials and try again." else "Log in again to resume syncing."),
                            style = Wv.small, color = Wv.c.text2,
                        )
                        PrimaryButton("Reconnect ${brokerName(b)}") { reconnect(b) }
                    }
                }
            }
            items(list, key = { it.connection_id }) { b ->
                BrokerCard(
                    b, syncing, usesKeys(b),
                    onSync = { vm.syncOne(b.connection_id) },
                    onReconnect = { reconnect(b) },
                    onKeys = itemFor(b)?.takeIf { it.credential_fields.isNotEmpty() }?.let { item -> { dialog = BrokerDialog.Keys(b, item) } },
                    onRemove = { dialog = BrokerDialog.Remove(b) },
                )
            }
            if (brokers.data?.isEmpty() == true) item { Note("No brokers connected. Press Add to link your first account.") }
            item {
                WvCard {
                    Text("How your data is handled", style = Wv.title, color = Wv.c.text)
                    Text("Applies to every connection on this page", style = Wv.small, color = Wv.c.text3)
                    listOf(
                        "Only read endpoints are called: holdings and prices. No order placement is ever requested.",
                        "API secrets and session tokens are encrypted before they are stored, and are never shown again after saving.",
                        "Daily-expiring sessions (Kite, Groww, SmartAPI) ask you to log in again instead of keeping a password.",
                        "Disconnecting deletes that broker's stored credentials and its synced holdings.",
                    ).forEach { t ->
                        Row(verticalAlignment = Alignment.Top) {
                            androidx.compose.material3.Icon(androidx.compose.material.icons.Icons.Outlined.CheckCircle, contentDescription = null, tint = Wv.c.gain, modifier = Modifier.size(16.dp).padding(top = 2.dp))
                            Spacer(Modifier.width(8.dp))
                            Text(t, style = Wv.small, color = Wv.c.text2)
                        }
                    }
                }
            }
        }
    }
    BrokerDialogs(dialog, avm, list, onDialog = { dialog = it }, onChanged = { vm.refreshAll() }, onSync = { vm.syncOne(it) })
}

/** "Just now", "12 min ago", "3 hr ago", "2d ago" */
fun relativeTime(iso: String?): String {
    if (iso.isNullOrBlank()) return "Never"
    val t = runCatching { java.time.OffsetDateTime.parse(iso).toInstant() }.getOrNull() ?: return "—"
    val mins = java.time.Duration.between(t, java.time.Instant.now()).toMinutes()
    return when {
        mins < 1 -> "Just now"
        mins < 60 -> "$mins min ago"
        mins < 60 * 24 -> "${mins / 60} hr ago"
        else -> "${mins / (60 * 24)}d ago"
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BrokerCard(b: BrokerSession, syncing: String?, usesKeys: Boolean, onSync: () -> Unit, onReconnect: () -> Unit, onKeys: (() -> Unit)?, onRemove: () -> Unit) {
    val (label, tone) = when {
        syncing == b.connection_id -> "Syncing" to Tone.Info
        b.status == "CONNECTED" -> "Connected" to Tone.Ok
        b.status == "SESSION_EXPIRED" -> "Session expired" to Tone.Warn
        b.status == "AUTH_REQUIRED" -> "Login needed" to Tone.Warn
        b.status == "DISCONNECTED" -> "Disconnected" to Tone.Off
        else -> "Problem" to Tone.Bad
    }
    val attn = needsLogin(b)
    val key = brokerKeyOf(b.connection_id).ifBlank { b.broker_name.lowercase() }
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(34.dp).clip(RoundedCornerShape(8.dp)).background(BROKER_COLORS[key] ?: Wv.c.text3), contentAlignment = Alignment.Center) {
                Text(brokerKeyLabel(key).take(1), style = Wv.title, color = androidx.compose.ui.graphics.Color.White)
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(brokerName(b), style = Wv.title, color = Wv.c.text, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    Badge(if (usesKeys) "API" else "MCP", Tone.Off)
                }
                Text(
                    listOfNotNull(b.account_label, b.account_id.ifBlank { null }?.let { "Client $it" }, hostOf(b.mcp_server_url)).joinToString(" · "),
                    style = Wv.small, color = Wv.c.text3, maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
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
                Text(relativeTime(b.last_sync_time), style = Wv.small, color = Wv.c.text2)
            }
        }
        // the session: why it needs attention, or how long it lasts
        Text(
            when {
                attn -> b.error_message?.takeIf { it.isNotBlank() } ?: if (usesKeys) "API credentials needed" else "Login required"
                !b.session_expires_at.isNullOrBlank() -> "Session valid until ${localTime(b.session_expires_at)}"
                else -> b.auth_type
            },
            style = Wv.small, color = if (attn) Wv.c.warn else Wv.c.text3,
        )
        if (!attn) b.error_message?.takeIf { it.isNotBlank() }?.let { Note(it, bad = true) }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.fillMaxWidth()) {
            if (attn) PrimaryButton(if (usesKeys) "Enter credentials" else "Reconnect", enabled = syncing == null) { onReconnect() }
            OutlinedButton(onClick = onSync, enabled = syncing == null, shape = RoundedCornerShape(10.dp)) {
                Text(if (syncing == b.connection_id) "Syncing…" else "Sync now", color = Wv.c.text)
            }
            if (onKeys != null && !attn) OutlinedButton(onClick = onKeys, shape = RoundedCornerShape(10.dp)) { Text("Credentials", color = Wv.c.text) }
            TextButton(onClick = onRemove) { Text("Disconnect", color = Wv.c.loss) }
        }
    }
}

private fun hostOf(url: String): String? = url.takeIf { it.isNotBlank() }?.let { runCatching { Uri.parse(it).host }.getOrNull() ?: it }

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
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Label("Hide amounts")
                        Text("Show every rupee amount as ₹ •••• (percentages stay). The eye button at the top of each page does the same.", style = Wv.small, color = Wv.c.text2)
                    }
                    androidx.compose.material3.Switch(
                        s.hideAmounts, { vm.setHideAmounts(it) },
                        colors = androidx.compose.material3.SwitchDefaults.colors(checkedTrackColor = Wv.c.accent, checkedThumbColor = Wv.c.onAccent, uncheckedTrackColor = Wv.c.surface2, uncheckedThumbColor = Wv.c.text3, uncheckedBorderColor = Wv.c.borderStrong),
                    )
                }
            }
        }
        item { AppLockCard(vm, s.lock) }
        item {
            WvCard {
                Label("Account")
                Text(s.email, style = Wv.body, color = Wv.c.text)
                Spacer(Modifier.height(4.dp))
                OutlinedButton(onClick = { vm.signOut() }, shape = RoundedCornerShape(10.dp)) { Text("Sign out", color = Wv.c.loss) }
            }
        }
        item { PrivacyCard(vm, s.baseUrl) }
        item { Text("Information from your brokers, not investment advice.", style = Wv.small, color = Wv.c.text3) }
        item { Text("WealthVault for Android ${com.wealthvault.app.BuildConfig.VERSION_NAME}", style = Wv.small, color = Wv.c.text3) }
    }
}

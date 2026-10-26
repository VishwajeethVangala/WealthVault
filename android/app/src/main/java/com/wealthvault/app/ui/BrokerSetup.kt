package com.wealthvault.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.wealthvault.app.data.BrokerCatalogItem
import com.wealthvault.app.data.BrokerSession
import com.wealthvault.app.data.CredentialSaveResponse

private fun parseColor(hex: String, fallback: Color): Color =
    runCatching { Color(android.graphics.Color.parseColor(hex)) }.getOrDefault(fallback)

/** Which step of broker set-up is showing. */
sealed interface BrokerDialog {
    data object Pick : BrokerDialog
    data class Name(val item: BrokerCatalogItem) : BrokerDialog
    data class Keys(val session: BrokerSession, val item: BrokerCatalogItem) : BrokerDialog
    data class Remove(val session: BrokerSession) : BrokerDialog
}

/**
 * The web app's broker set-up on a phone: pick a broker from the server's catalog, name the account, then either
 * enter its API keys (Angel One) or log in on the broker's own page (Zerodha, INDmoney, Groww).
 */
@Composable
fun BrokerDialogs(dialog: BrokerDialog?, avm: AnalysisViewModel, existing: List<BrokerSession>, onDialog: (BrokerDialog?) -> Unit, onChanged: () -> Unit, onSync: (String) -> Unit = {}) {
    val catalog by avm.catalog.collectAsState()
    val busy by avm.brokerBusy.collectAsState()
    val context = LocalContext.current
    val open = { url: String -> openLink(context, url) }

    when (dialog) {
        null -> Unit
        BrokerDialog.Pick -> AlertDialog(
            onDismissRequest = { onDialog(null) },
            containerColor = Wv.c.surface,
            title = { Text("Add a broker", color = Wv.c.text) },
            text = {
                Column(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    catalog.problem?.let { Note(it.text, bad = true) }
                    if (catalog.loading && catalog.data == null) Text("Loading brokers…", style = Wv.sub, color = Wv.c.text3)
                    catalog.data.orEmpty().sortedBy { !it.supported }.forEach { item ->
                        val usable = item.supported && !item.coming_soon
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(10.dp))
                                .background(Wv.c.surface2)
                                .then(if (usable) Modifier.clickable { onDialog(BrokerDialog.Name(item)) } else Modifier)
                                .padding(10.dp),
                        ) {
                            Box(Modifier.size(34.dp).clip(RoundedCornerShape(8.dp)).background(parseColor(item.color, Wv.c.text3)), contentAlignment = Alignment.Center) {
                                Text(item.tag.take(3), style = Wv.small.copy(fontWeight = FontWeight.SemiBold), color = Color.White)
                            }
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(item.display_name, style = Wv.title, color = if (usable) Wv.c.text else Wv.c.text3)
                                Text(item.auth_type, style = Wv.small, color = Wv.c.text3)
                            }
                            when {
                                !usable -> Badge("Coming soon", Tone.Off)
                                item.connected_count > 0 -> Badge("${item.connected_count} connected", Tone.Ok)
                            }
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { onDialog(null) }) { Text("Close", color = Wv.c.text2) } },
        )

        is BrokerDialog.Name -> {
            val item = dialog.item
            val count = existing.count { it.broker_name.equals(item.broker_name, ignoreCase = true) }
            var label by remember(item) { mutableStateOf(if (count > 0) "Account ${count + 1}" else "") }
            var clientId by remember(item) { mutableStateOf("") }
            AlertDialog(
                onDismissRequest = { onDialog(null) },
                containerColor = Wv.c.surface,
                title = { Text("Connect ${item.display_name}", color = Wv.c.text) },
                text = {
                    Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(item.description, style = Wv.sub, color = Wv.c.text2)
                        OutlinedTextField(label, { label = it }, label = { Text("Account label") }, placeholder = { Text("e.g. Personal, Family HUF") }, supportingText = { Text("Tells this account apart from other ${item.display_name.substringBefore(" — ")} accounts.") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(clientId, { clientId = it.trim() }, label = { Text("Client ID (optional)") }, placeholder = { Text("Shown on the card for reference") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                        if (item.setup_steps.isNotEmpty()) {
                            Label("Before you start")
                            item.setup_steps.forEachIndexed { i, step -> Text("${i + 1}. $step", style = Wv.small, color = Wv.c.text2) }
                            item.setup_url?.let { url -> TextButton(onClick = { open(url) }) { Text("Open ${item.display_name}'s API page", color = Wv.c.accent) } }
                        }
                        Text(
                            if (item.credential_fields.isNotEmpty()) "Next you enter your API keys. They are stored encrypted on the server and never shown again."
                            else "Next the broker's login page opens in your browser. Come back here and press Sync now when you're done.",
                            style = Wv.small, color = Wv.c.text3,
                        )
                    }
                },
                confirmButton = {
                    TextButton(enabled = !busy, onClick = {
                        avm.addConnection(item, label, clientId) { created ->
                            onChanged()
                            if (item.credential_fields.isNotEmpty()) onDialog(BrokerDialog.Keys(created, item))
                            else {
                                onDialog(null)
                                created.auth_url?.let(open)
                            }
                        }
                    }) { Text(if (busy) "Adding…" else "Add", color = Wv.c.accent) }
                },
                dismissButton = { TextButton(onClick = { onDialog(null) }) { Text("Cancel", color = Wv.c.text2) } },
            )
        }

        is BrokerDialog.Keys -> {
            val values = remember(dialog) { mutableStateMapOf<String, String>() }
            var result by remember(dialog) { mutableStateOf<CredentialSaveResponse?>(null) }
            val fields = dialog.item.credential_fields
            val ready = fields.filter { it.required }.all { !values[it.key].isNullOrBlank() } && values.values.any { it.isNotBlank() }
            AlertDialog(
                onDismissRequest = { onDialog(null) },
                containerColor = Wv.c.surface,
                title = { Text("${dialog.item.display_name} API keys", color = Wv.c.text) },
                text = {
                    Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (result == null) {
                            Text("Stored encrypted on the server for this connection only, and never sent back to the app. Leave a field empty to keep what is saved.", style = Wv.small, color = Wv.c.text3)
                            fields.forEach { f ->
                                OutlinedTextField(
                                    values[f.key].orEmpty(), { values[f.key] = it.trim() },
                                    label = { Text(f.label + if (f.required) "" else " (optional)") },
                                    supportingText = f.help?.let { h -> { Text(h) } },
                                    singleLine = true,
                                    visualTransformation = if (f.secret) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
                                    keyboardOptions = KeyboardOptions(keyboardType = if (f.secret) KeyboardType.Password else KeyboardType.Text, autoCorrectEnabled = false),
                                    modifier = Modifier.fillMaxWidth(),
                                )
                            }
                        } else {
                            val r = result!!
                            Note(r.message.ifBlank { if (r.login_ok) "Saved, and the broker accepted the keys." else "Saved." }, bad = !r.login_ok)
                            r.auth_url?.let { url -> TextButton(onClick = { open(url) }) { Text("Approve on ${dialog.item.display_name}", color = Wv.c.accent) } }
                        }
                    }
                },
                confirmButton = {
                    if (result == null) {
                        TextButton(enabled = ready && !busy, onClick = {
                            avm.saveCredentials(dialog.session.connection_id, values.filterValues { it.isNotBlank() }) {
                                result = it
                                onChanged()
                                // the keys work: pull the holdings now, as the web does
                                if (it.login_ok) onSync(dialog.session.connection_id)
                            }
                        }) { Text(if (busy) "Saving…" else "Save", color = if (ready) Wv.c.accent else Wv.c.text3) }
                    } else {
                        TextButton(onClick = { onDialog(null) }) { Text("Done", color = Wv.c.accent) }
                    }
                },
                dismissButton = { if (result == null) TextButton(onClick = { onDialog(null) }) { Text("Cancel", color = Wv.c.text2) } },
            )
        }

        is BrokerDialog.Remove -> {
            var wipe by remember(dialog) { mutableStateOf(true) }
            AlertDialog(
                onDismissRequest = { onDialog(null) },
                containerColor = Wv.c.surface,
                title = { Text("Disconnect ${brokerName(dialog.session)}?", color = Wv.c.text) },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("This removes the connection and its synced data from your vault. Your account at the broker is not touched, and you can add it again later.", style = Wv.sub, color = Wv.c.text2)
                        dialog.session.account_label?.let { StatLine("Account", it) }
                        StatLine("Holdings removed", "${dialog.session.holdings_count}")
                        StatLine("Value removed from net worth", compact(dialog.session.total_valuation))
                        Row(verticalAlignment = Alignment.Top, modifier = Modifier.clickable { wipe = !wipe }) {
                            androidx.compose.material3.Checkbox(wipe, { wipe = it }, colors = androidx.compose.material3.CheckboxDefaults.colors(checkedColor = Wv.c.accent, uncheckedColor = Wv.c.text3))
                            Column(Modifier.padding(top = 12.dp)) {
                                Text("Also delete archived raw broker responses", style = Wv.sub.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                                Text("The JSON snapshots kept in storage for this connection.", style = Wv.small, color = Wv.c.text3)
                            }
                        }
                    }
                },
                confirmButton = {
                    TextButton(enabled = !busy, onClick = { avm.removeConnection(dialog.session.connection_id, wipe) { onDialog(null); onChanged() } }) {
                        Text(if (busy) "Disconnecting…" else "Disconnect", color = Wv.c.loss)
                    }
                },
                dismissButton = { TextButton(onClick = { onDialog(null) }) { Text("Cancel", color = Wv.c.text2) } },
            )
        }
    }
}

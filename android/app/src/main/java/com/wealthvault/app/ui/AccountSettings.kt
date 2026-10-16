package com.wealthvault.app.ui

import androidx.compose.ui.unit.dp
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext

/** Turn the app lock on or off. Either way the person must pass the check, so a borrowed phone cannot change it. */
@Composable
fun AppLockCard(vm: AppViewModel, on: Boolean) {
    val context = LocalContext.current
    val activity = context.findFragmentActivity()
    var note by remember { mutableStateOf<String?>(null) }
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Label("App lock")
                Text("Ask for your fingerprint, face or screen lock each time the app is opened.", style = Wv.sub, color = Wv.c.text2)
            }
            Switch(
                checked = on,
                onCheckedChange = { want ->
                    note = null
                    when {
                        activity == null -> Unit
                        want && !AppLock.available(context) ->
                            note = "Set up a fingerprint, face or screen lock in your phone's settings first, then come back."
                        else -> AppLock.prompt(
                            activity,
                            if (want) "Turn on app lock" else "Turn off app lock",
                            "Confirm it is you",
                            onSuccess = { vm.setLock(want) },
                            onFailure = { note = it },
                        )
                    }
                },
                colors = SwitchDefaults.colors(
                    checkedTrackColor = Wv.c.accent, checkedThumbColor = Wv.c.onAccent,
                    uncheckedTrackColor = Wv.c.surface2, uncheckedThumbColor = Wv.c.text3, uncheckedBorderColor = Wv.c.borderStrong,
                ),
            )
        }
        note?.let { Note(it) }
        if (on) Text("The screen is hidden from screenshots and the recent-apps view while the lock is on.", style = Wv.small, color = Wv.c.text3)
    }
}

/** Privacy policy, how deletion works, and "Delete my account". */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PrivacyCard(vm: AppViewModel, baseUrl: String) {
    val context = LocalContext.current
    val open = { path: String -> context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(baseUrl + path))) }
    WvCard {
        Label("Privacy and data")
        Text(
            "WealthVault keeps your holdings and settings on its server, separate for each user. You can read how, or erase everything.",
            style = Wv.sub, color = Wv.c.text2,
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { open("/privacy") }, shape = RoundedCornerShape(10.dp)) { Text("Privacy policy", color = Wv.c.text) }
            OutlinedButton(onClick = { open("/delete-account") }, shape = RoundedCornerShape(10.dp)) { Text("How deletion works", color = Wv.c.text) }
        }
        DeleteAccount(vm)
    }
}

/** "Delete my account": explains what goes, and asks for the word DELETE before anything is erased. */
@Composable
private fun DeleteAccount(vm: AppViewModel) {
    val deleting by vm.deleting.collectAsState()
    val message by vm.message.collectAsState()
    var asking by remember { mutableStateOf(false) }
    var typed by remember { mutableStateOf("") }
    HorizontalDivider(color = Wv.c.border)
    OutlinedButton(onClick = { typed = ""; asking = true }, shape = RoundedCornerShape(10.dp)) { Text("Delete my account", color = Wv.c.loss) }
    message?.let { Note(it, bad = true) }
    if (asking) {
        AlertDialog(
            onDismissRequest = { if (!deleting) asking = false },
            containerColor = Wv.c.surface,
            title = { Text("Delete your account?", color = Wv.c.text) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        "This erases your profile, all holdings and history, your targets, your broker connections and saved broker logins from WealthVault, now and for good. It does not touch your accounts at the brokers.",
                        style = Wv.sub, color = Wv.c.text2,
                    )
                    OutlinedTextField(typed, { typed = it }, label = { Text("Type DELETE to confirm") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                }
            },
            confirmButton = {
                TextButton(enabled = typed.trim() == "DELETE" && !deleting, onClick = { vm.deleteAccount() }) {
                    Text(if (deleting) "Deleting…" else "Delete everything", color = if (typed.trim() == "DELETE") Wv.c.loss else Wv.c.text3)
                }
            },
            dismissButton = { TextButton(enabled = !deleting, onClick = { asking = false }) { Text("Cancel", color = Wv.c.text2) } },
        )
    }
}

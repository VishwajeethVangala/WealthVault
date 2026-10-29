package com.wealthvault.app.ui

import android.Manifest
import android.content.Intent
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat

/** Asked once, on Android 13 and later where the phone itself asks permission to show notifications. */
@Composable
fun NotificationsPromptScreen(vm: AppViewModel) {
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { vm.setNotifAsked() }
    Column(
        Modifier.fillMaxSize().background(Wv.c.bg).padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.Start,
    ) {
        Box(Modifier.size(48.dp).clip(RoundedCornerShape(12.dp)).background(Wv.c.text), contentAlignment = Alignment.Center) {
            Text("W", color = Wv.c.bg, style = Wv.title)
        }
        Spacer(Modifier.height(20.dp))
        Text("Get alerts that matter", style = Wv.h1, color = Wv.c.text)
        Text(
            "ATH strategy calls on the stocks you hold, a daily and weekly net worth update, and a reminder when Kite needs its morning login. " +
                "On the lock screen only a plain line shows, never a stock name or an amount. You can switch each kind off in Settings.",
            style = Wv.sub, color = Wv.c.text3,
        )
        Spacer(Modifier.height(24.dp))
        PrimaryButton("Turn on notifications", modifier = Modifier.fillMaxWidth()) {
            launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = { vm.setNotifAsked() }, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
            Text("Not now", color = Wv.c.text)
        }
    }
}

private val KINDS = listOf(
    "holdings_ath" to "ATH calls on my holdings",
    "stage2_ath" to "ATH calls on the Stage 2 list",
    "networth_daily" to "Daily net worth, after the close",
    "networth_weekly" to "Weekly net worth, Sunday morning",
    "kite_login" to "Kite login reminder, mornings",
)

/** Settings: which notifications to get, a test button, and a pointer to the phone's own settings if they are blocked. */
@Composable
fun NotificationsCard(vm: AppViewModel) {
    val context = LocalContext.current
    val prefs by vm.notifPrefs.collectAsState()
    val message by vm.notifMessage.collectAsState()
    LaunchedEffect(Unit) { vm.loadNotifPrefs() }
    val allowed = NotificationManagerCompat.from(context).areNotificationsEnabled()
    WvCard {
        Label("Notifications")
        Text("Choose what to be told about. The lock screen never shows stock names or amounts.", style = Wv.sub, color = Wv.c.text2)
        if (!allowed) {
            Note("Notifications are switched off for WealthVault on this phone.")
            OutlinedButton(
                onClick = {
                    context.startActivity(
                        Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                    )
                },
                shape = RoundedCornerShape(10.dp),
            ) { Text("Open phone notification settings", color = Wv.c.accent) }
        }
        KINDS.forEach { (key, label) ->
            HorizontalDivider(color = Wv.c.border)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(label, style = Wv.sub, color = Wv.c.text, modifier = Modifier.weight(1f))
                Switch(
                    checked = prefs?.get(key) ?: true,
                    onCheckedChange = { vm.setNotifPref(key, it) },
                    enabled = prefs != null,
                    colors = SwitchDefaults.colors(
                        checkedTrackColor = Wv.c.accent, checkedThumbColor = Wv.c.onAccent,
                        uncheckedTrackColor = Wv.c.surface2, uncheckedThumbColor = Wv.c.text3, uncheckedBorderColor = Wv.c.borderStrong,
                    ),
                )
            }
        }
        HorizontalDivider(color = Wv.c.border)
        OutlinedButton(onClick = { vm.testNotification() }, enabled = allowed, shape = RoundedCornerShape(10.dp)) {
            Text("Send me a test notification", color = Wv.c.accent)
        }
        message?.let { Note(it) }
    }
}

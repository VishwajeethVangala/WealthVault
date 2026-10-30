package com.wealthvault.app.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.google.android.play.core.appupdate.AppUpdateInfo
import com.google.android.play.core.appupdate.AppUpdateManagerFactory
import com.google.android.play.core.appupdate.AppUpdateOptions
import com.google.android.play.core.install.InstallStateUpdatedListener
import com.google.android.play.core.install.model.AppUpdateType
import com.google.android.play.core.install.model.InstallStatus
import com.google.android.play.core.install.model.UpdateAvailability

/**
 * A thin bar under the top strip when Google Play has a newer version: "Update" downloads it in the background while the
 * app stays usable, then "Restart" installs it. Nothing shows when the app was not installed from Play, when there is
 * no update, or after the person closes the bar (it comes back at the next opening).
 */
@Composable
fun UpdateBanner() {
    val context = LocalContext.current
    val manager = remember { AppUpdateManagerFactory.create(context) }
    var available by remember { mutableStateOf<AppUpdateInfo?>(null) }
    var downloading by remember { mutableStateOf(false) }
    var ready by remember { mutableStateOf(false) }
    var dismissed by rememberSaveable { mutableStateOf(false) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) { }

    DisposableEffect(manager) {
        val listener = InstallStateUpdatedListener { state ->
            when (state.installStatus()) {
                InstallStatus.DOWNLOADED -> { downloading = false; ready = true }
                InstallStatus.FAILED, InstallStatus.CANCELED -> downloading = false
                else -> Unit
            }
        }
        manager.registerListener(listener)
        manager.appUpdateInfo
            .addOnSuccessListener { info ->
                if (info.installStatus() == InstallStatus.DOWNLOADED) ready = true
                else if (info.updateAvailability() == UpdateAvailability.UPDATE_AVAILABLE && info.isUpdateTypeAllowed(AppUpdateType.FLEXIBLE)) available = info
            }
            .addOnFailureListener { } // not installed from Play, or no network: nothing to offer
        onDispose { manager.unregisterListener(listener) }
    }

    val text = when {
        ready -> "Update downloaded. Restart to finish."
        downloading -> "Downloading the update…"
        available != null -> "A new version of WealthVault is available."
        else -> return
    }
    if (dismissed && !ready) return
    Row(
        Modifier.fillMaxWidth().background(Wv.c.accentWeak).padding(start = 16.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(text, style = Wv.small, color = Wv.c.text, modifier = Modifier.weight(1f))
        when {
            ready -> TextButton(onClick = { manager.completeUpdate() }) { Text("Restart", color = Wv.c.accent) }
            downloading -> Unit
            else -> {
                TextButton(onClick = {
                    available?.let { info ->
                        runCatching { manager.startUpdateFlowForResult(info, launcher, AppUpdateOptions.newBuilder(AppUpdateType.FLEXIBLE).build()) }
                            .onSuccess { downloading = true }
                    }
                }) { Text("Update", color = Wv.c.accent) }
                TextButton(onClick = { dismissed = true }) { Text("Later", color = Wv.c.text3) }
            }
        }
    }
}

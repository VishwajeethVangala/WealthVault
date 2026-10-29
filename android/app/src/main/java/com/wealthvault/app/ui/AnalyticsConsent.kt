package com.wealthvault.app.ui

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
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp

/** Asked once after sign-in (and the app lock step). Nothing is collected until the person taps Allow. */
@Composable
fun AnalyticsConsentScreen(vm: AppViewModel) {
    Column(
        Modifier.fillMaxSize().background(Wv.c.bg).padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.Start,
    ) {
        Box(Modifier.size(48.dp).clip(RoundedCornerShape(12.dp)).background(Wv.c.text), contentAlignment = Alignment.Center) {
            Text("W", color = Wv.c.bg, style = Wv.title)
        }
        Spacer(Modifier.height(20.dp))
        Text("Help improve WealthVault", style = Wv.h1, color = Wv.c.text)
        Text(
            "Share which screens you use, what you search for, and crash reports, so we can fix what is slow or missing. " +
                "Never your amounts, holdings, email or name. You can change this any time in Settings.",
            style = Wv.sub, color = Wv.c.text3,
        )
        Spacer(Modifier.height(24.dp))
        PrimaryButton("Allow", modifier = Modifier.fillMaxWidth()) { vm.setAnalytics(true) }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = { vm.setAnalytics(false) }, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
            Text("Not now", color = Wv.c.text)
        }
    }
}

/** The Settings switch for the same choice. */
@Composable
fun AnalyticsCard(vm: AppViewModel, on: Boolean) {
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Label("Usage data and crash reports")
                Text(
                    "Share which screens you use, what you search for, and crash reports. Never amounts, holdings or personal details.",
                    style = Wv.sub, color = Wv.c.text2,
                )
            }
            Switch(
                checked = on,
                onCheckedChange = { vm.setAnalytics(it) },
                colors = SwitchDefaults.colors(
                    checkedTrackColor = Wv.c.accent, checkedThumbColor = Wv.c.onAccent,
                    uncheckedTrackColor = Wv.c.surface2, uncheckedThumbColor = Wv.c.text3, uncheckedBorderColor = Wv.c.borderStrong,
                ),
            )
        }
    }
}

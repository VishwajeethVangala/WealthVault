package com.wealthvault.app.ui

import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import android.content.Context
import android.content.ContextWrapper
import android.os.Build
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.material3.TextButton
import android.content.Intent
import android.provider.Settings
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.currentStateAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity

/**
 * The optional app lock. Android does the check itself (fingerprint, face, or the phone's PIN, pattern or password);
 * WealthVault never sees or stores any of it.
 */
object AppLock {
    /** Fingerprint or face, plus the phone's screen lock where Android 11+ allows combining them. */
    private val allowed: Int
        get() = if (Build.VERSION.SDK_INT >= 30) {
            BiometricManager.Authenticators.BIOMETRIC_WEAK or BiometricManager.Authenticators.DEVICE_CREDENTIAL
        } else {
            BiometricManager.Authenticators.BIOMETRIC_WEAK
        }

    /** True when the phone has something to check against (an enrolled fingerprint or face, or a screen lock). */
    fun available(context: Context): Boolean = BiometricManager.from(context).canAuthenticate(allowed) == BiometricManager.BIOMETRIC_SUCCESS

    fun prompt(activity: FragmentActivity, title: String, subtitle: String, onSuccess: () -> Unit, onFailure: (String) -> Unit = {}) {
        val callback = object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) = onSuccess()
            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) = onFailure(errString.toString())
        }
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle(subtitle)
            .setAllowedAuthenticators(allowed)
            .apply { if (Build.VERSION.SDK_INT < 30) setNegativeButtonText("Cancel") }
            .build()
        BiometricPrompt(activity, ContextCompat.getMainExecutor(activity), callback).authenticate(info)
    }
}

fun Context.findFragmentActivity(): FragmentActivity? {
    var c: Context? = this
    while (c is ContextWrapper) {
        if (c is FragmentActivity) return c
        c = c.baseContext
    }
    return null
}

/** Shown instead of the app while the lock is on and the person has not yet unlocked it. */
@Composable
fun LockScreen(onUnlocked: () -> Unit) {
    val activity = LocalContext.current.findFragmentActivity()
    var note by remember { mutableStateOf<String?>(null) }
    val ask = {
        activity?.let { a -> AppLock.prompt(a, "Unlock WealthVault", "Confirm it is you", onSuccess = onUnlocked, onFailure = { note = it }) }
        Unit
    }
    // ask straight away, so a normal open is one touch
    LaunchedEffect(Unit) { ask() }
    Column(
        Modifier.fillMaxSize().background(Wv.c.bg).padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.Start,
    ) {
        Box(Modifier.size(48.dp).clip(RoundedCornerShape(12.dp)).background(Wv.c.text), contentAlignment = Alignment.Center) {
            Text("W", color = Wv.c.bg, style = Wv.title)
        }
        Spacer(Modifier.height(20.dp))
        Text("WealthVault is locked", style = Wv.h1, color = Wv.c.text)
        Text("Unlock with your fingerprint, face or screen lock.", style = Wv.sub, color = Wv.c.text3)
        Spacer(Modifier.height(24.dp))
        PrimaryButton("Unlock", modifier = Modifier.fillMaxWidth()) { ask() }
        note?.let {
            Spacer(Modifier.height(12.dp))
            Note(it)
        }
    }
}



/**
 * First thing a signed-in person sees until app lock is on. It is required, with no skip. The one exception is a phone
 * with no screen lock at all: the app cannot check anything there, so it points to the phone's settings and lets the
 * person in meanwhile rather than shutting them out of their own data.
 */
@Composable
fun LockSetupScreen(vm: AppViewModel) {
    val context = LocalContext.current
    val activity = context.findFragmentActivity()
    var note by remember { mutableStateOf<String?>(null) }
    // the person may set a screen lock in the phone's settings and come back: look again then
    val state by LocalLifecycleOwner.current.lifecycle.currentStateAsState()
    val available = remember(state) { AppLock.available(context) }
    Column(
        Modifier.fillMaxSize().background(Wv.c.bg).padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.Start,
    ) {
        Box(Modifier.size(48.dp).clip(RoundedCornerShape(12.dp)).background(Wv.c.text), contentAlignment = Alignment.Center) {
            Text("W", color = Wv.c.bg, style = Wv.title)
        }
        Spacer(Modifier.height(20.dp))
        Text("Protect your portfolio", style = Wv.h1, color = Wv.c.text)
        Text(
            "WealthVault shows your holdings and net worth, so the app now opens only after your fingerprint, face or screen lock. It takes a few seconds, and WealthVault never sees any of it.",
            style = Wv.sub, color = Wv.c.text3,
        )
        Spacer(Modifier.height(24.dp))
        if (available) {
            PrimaryButton("Turn on app lock", modifier = Modifier.fillMaxWidth()) {
                note = null
                activity?.let { a -> AppLock.prompt(a, "Turn on app lock", "Confirm it is you", onSuccess = { vm.setLock(true) }, onFailure = { note = it }) }
            }
        } else {
            Note("This phone has no screen lock yet. Set a fingerprint, face, PIN or pattern in the phone's settings, then come back.")
            Spacer(Modifier.height(12.dp))
            PrimaryButton("Open phone security settings", modifier = Modifier.fillMaxWidth()) {
                context.startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            TextButton(onClick = { vm.lockSetupSkipped.value = true }, modifier = Modifier.fillMaxWidth()) { Text("Continue without it for now", color = Wv.c.text2) }
        }
        note?.let {
            Spacer(Modifier.height(12.dp))
            Note(it)
        }
        TextButton(onClick = { vm.signOut() }, modifier = Modifier.fillMaxWidth()) { Text("Sign out", color = Wv.c.text3) }
    }
}

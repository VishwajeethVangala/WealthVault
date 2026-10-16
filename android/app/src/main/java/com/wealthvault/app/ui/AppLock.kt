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



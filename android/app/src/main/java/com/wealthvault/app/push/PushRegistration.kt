package com.wealthvault.app.push

import android.content.Context
import com.google.firebase.messaging.FirebaseMessaging
import com.wealthvault.app.data.Api
import com.wealthvault.app.data.Prefs
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

/** Tells the server which phone belongs to the signed-in person, so their notifications reach this phone only. */
object PushRegistration {
    private suspend fun currentToken(): String? = suspendCoroutine { cont ->
        runCatching {
            FirebaseMessaging.getInstance().token.addOnCompleteListener { t -> cont.resume(if (t.isSuccessful) t.result else null) }
        }.onFailure { cont.resume(null) }
    }

    /** Registers this phone for the signed-in person (does nothing when signed out). */
    suspend fun registerCurrent(context: Context) {
        val token = currentToken() ?: return
        register(context, token)
    }

    suspend fun register(context: Context, token: String) {
        val prefs = Prefs(context)
        if (prefs.current().token == null) return
        runCatching {
            Api(prefs).registerDevice(token)
            prefs.saveFcmToken(token)
        }
    }

    /** Forgets this phone on the server; call before signing out so the next person on it gets nothing meant for this one. */
    suspend fun unregister(context: Context) {
        val prefs = Prefs(context)
        val token = prefs.fcmToken() ?: return
        runCatching { Api(prefs).removeDevice(token) }
        prefs.saveFcmToken(null)
    }
}

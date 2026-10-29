package com.wealthvault.app.push

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.wealthvault.app.data.Api
import com.wealthvault.app.data.Prefs
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull

/** Receives WealthVault's push messages (a type and an id), fetches the text from the server, and shows it. */
class WvMessagingService : FirebaseMessagingService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        scope.launch { PushRegistration.register(applicationContext, token) }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val kind = message.data["type"] ?: return
        val id = message.data["id"] ?: return
        // this runs on a background thread with about 20 seconds to finish, so the fetch is cut off well before that
        runBlocking(Dispatchers.IO) {
            val prefs = Prefs(applicationContext)
            val session = prefs.current()
            if (session.token == null) return@runBlocking // signed out: nothing to show
            val note = withTimeoutOrNull(10_000) { runCatching { Api(prefs).notification(id) }.getOrNull() }
            Notifier.show(applicationContext, kind, id, note, session.hideAmounts)
        }
    }
}

package com.wealthvault.app.push

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.wealthvault.app.MainActivity
import com.wealthvault.app.R
import com.wealthvault.app.data.PushNote

/**
 * Builds and shows WealthVault's notifications. The push message only says what kind it is and gives an id; the text
 * is fetched from WealthVault's own server and put together here, so names and amounts never ride on Google's push
 * service. On the lock screen only a plain "update is ready" line shows; the details appear after unlocking.
 */
object Notifier {
    const val EXTRA_OPEN = "wv_open"
    const val EXTRA_KIND = "wv_notif"

    private const val CH_HOLDINGS = "ath_holdings"
    private const val CH_STAGE2 = "ath_stage2"
    private const val CH_NETWORTH = "networth"
    private const val CH_KITE = "kite_login"
    private const val CH_GENERAL = "general"

    fun ensureChannels(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        fun channel(id: String, name: String, description: String, importance: Int) {
            val c = NotificationChannel(id, name, importance).apply {
                this.description = description
                lockscreenVisibility = android.app.Notification.VISIBILITY_PRIVATE
            }
            manager.createNotificationChannel(c)
        }
        channel(CH_HOLDINGS, "ATH calls on your holdings", "Entry and exit calls from the ATH strategy on stocks you hold", NotificationManager.IMPORTANCE_HIGH)
        channel(CH_STAGE2, "ATH calls on the Stage 2 list", "Entry and exit calls from the ATH strategy on the Stage 2 list", NotificationManager.IMPORTANCE_DEFAULT)
        channel(CH_NETWORTH, "Net worth updates", "Your daily and weekly net worth", NotificationManager.IMPORTANCE_DEFAULT)
        channel(CH_KITE, "Kite login reminders", "A morning reminder when Kite needs today's login", NotificationManager.IMPORTANCE_DEFAULT)
        channel(CH_GENERAL, "Other", "Test messages", NotificationManager.IMPORTANCE_DEFAULT)
    }

    private fun channelFor(kind: String) = when {
        kind == "ath_h" || kind == "ath_reversed" -> CH_HOLDINGS
        kind == "ath_s" -> CH_STAGE2
        kind.startsWith("networth") -> CH_NETWORTH
        kind == "kite_login" -> CH_KITE
        else -> CH_GENERAL
    }

    /** Shows one notification. [note] is null when the text could not be fetched; a plain line is shown then. */
    fun show(context: Context, kind: String, id: String, note: PushNote?, hideAmounts: Boolean) {
        ensureChannels(context)
        val manager = NotificationManagerCompat.from(context)
        if (!manager.areNotificationsEnabled()) return
        val channel = channelFor(kind)
        val title = note?.title?.takeIf { it.isNotBlank() } ?: "WealthVault"
        val body = when {
            note == null -> "Open WealthVault to see the latest."
            hideAmounts -> note.body_masked.ifBlank { note.body }
            else -> note.body
        }
        val publicTitle = note?.public_title?.takeIf { it.isNotBlank() } ?: "WealthVault update"
        val open = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra(EXTRA_OPEN, note?.route?.takeIf { it.isNotBlank() } ?: "overview")
            putExtra(EXTRA_KIND, kind)
        }
        val tap = PendingIntent.getActivity(context, id.hashCode(), open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val lockScreen = NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_stat_wv)
            .setContentTitle(publicTitle)
            .setContentText("Open WealthVault to see more")
            .build()
        val n = NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_stat_wv)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(if (channel == CH_HOLDINGS) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(lockScreen)
            .setContentIntent(tap)
            .setAutoCancel(true)
            .build()
        runCatching { manager.notify(id.hashCode(), n) } // a missing permission just means nothing is shown
    }
}

package com.wealthvault.app.push

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.wealthvault.app.MainActivity
import com.wealthvault.app.R
import com.wealthvault.app.data.PushNote
import org.json.JSONObject

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
    private const val CH_US = "us_stocks"
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
        channel(CH_HOLDINGS, "Strategy calls on your holdings", "Entry and exit calls from the strategy on stocks you hold", NotificationManager.IMPORTANCE_HIGH)
        channel(CH_STAGE2, "Strategy calls on the Stage 2 list", "Entry and exit calls from the strategy on the Stage 2 list", NotificationManager.IMPORTANCE_DEFAULT)
        channel(CH_NETWORTH, "Net worth updates", "Your daily and weekly net worth", NotificationManager.IMPORTANCE_DEFAULT)
        channel(CH_US, "US stocks", "A mid-session look at your US stocks on US trading days", NotificationManager.IMPORTANCE_DEFAULT)
        channel(CH_KITE, "Kite login reminders", "A morning reminder when Kite needs today's login", NotificationManager.IMPORTANCE_DEFAULT)
        channel(CH_GENERAL, "Other", "Test messages", NotificationManager.IMPORTANCE_DEFAULT)
    }

    private fun channelFor(kind: String) = when {
        kind == "ath_h" || kind == "ath_reversed" -> CH_HOLDINGS
        kind == "ath_s" -> CH_STAGE2
        kind.startsWith("networth") -> CH_NETWORTH
        kind == "us_digest" -> CH_US
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
        val extra = runCatching { JSONObject(note?.extra.orEmpty().ifBlank { "{}" }) }.getOrDefault(JSONObject())
        val tap = PendingIntent.getActivity(context, id.hashCode(), openIntent(context, kind, note?.route), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val lockScreen = NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_stat_wv)
            .setContentTitle(publicTitle)
            .setContentText("Open WealthVault to see more")
            .build()
        val builder = NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_stat_wv)
            .setContentTitle(title)
            .setContentText(body.lineSequence().firstOrNull().orEmpty()) // the folded view shows the first line; pulling it down shows all
            .setPriority(if (channel == CH_HOLDINGS) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(lockScreen)
            .setContentIntent(tap)
            .setAutoCancel(true)
            .setColor(accent(extra.optString("tone")))
        val series = extra.optJSONArray("series")?.let { a -> List(a.length()) { a.optDouble(it) } }.orEmpty()
        if (series.size >= 3) {
            // the week as a line indexed to 100: its shape shows how the week went and it holds no amount
            builder.setStyle(
                NotificationCompat.BigPictureStyle().bigPicture(sparkline(series, accent(extra.optString("tone")))).bigLargeIcon(null as Bitmap?).setSummaryText(body),
            )
        } else {
            builder.setStyle(NotificationCompat.BigTextStyle().bigText(body))
        }
        // action buttons, each opening its own page
        extra.optJSONArray("actions")?.let { acts ->
            for (i in 0 until minOf(acts.length(), 3)) {
                val a = acts.optJSONObject(i) ?: continue
                val label = a.optString("label")
                val route = a.optString("route")
                if (label.isBlank() || route.isBlank()) continue
                val pi = PendingIntent.getActivity(context, id.hashCode() * 31 + i + 1, openIntent(context, kind, route), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
                builder.addAction(0, label, pi)
            }
        }
        runCatching { manager.notify(id.hashCode(), builder.build()) } // a missing permission just means nothing is shown
    }

    private fun openIntent(context: Context, kind: String, route: String?) = Intent(context, MainActivity::class.java).apply {
        flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
        putExtra(EXTRA_OPEN, route?.takeIf { it.isNotBlank() } ?: "overview")
        putExtra(EXTRA_KIND, kind)
    }

    /** Green for a good day or an entry call, red for a bad day or an exit call, the app's grey-blue otherwise. */
    private fun accent(tone: String) = when (tone) {
        "up" -> Color.rgb(0x1E, 0x8E, 0x5A)
        "down" -> Color.rgb(0xC0, 0x39, 0x2B)
        else -> Color.rgb(0x5B, 0x6B, 0x7B)
    }

    /** A small line chart of [values] (any scale) as a picture for the expanded notification. */
    private fun sparkline(values: List<Double>, color: Int): Bitmap {
        val w = 720
        val h = 260
        val pad = 28f
        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        c.drawColor(Color.rgb(0xF4, 0xF6, 0xF8))
        val lo = values.min()
        val hi = values.max()
        val span = (hi - lo).takeIf { it > 1e-9 } ?: 1.0
        fun x(i: Int) = pad + (w - 2 * pad) * i / (values.size - 1)
        fun y(v: Double) = (h - pad - (h - 2 * pad) * ((v - lo) / span)).toFloat()
        val line = Path().apply {
            values.forEachIndexed { i, v -> if (i == 0) moveTo(x(i), y(v)) else lineTo(x(i), y(v)) }
        }
        val fill = Path(line).apply { lineTo(x(values.size - 1), h - pad); lineTo(x(0), h - pad); close() }
        c.drawPath(fill, Paint(Paint.ANTI_ALIAS_FLAG).apply { this.color = Color.argb(40, Color.red(color), Color.green(color), Color.blue(color)) })
        c.drawPath(line, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            this.color = color; style = Paint.Style.STROKE; strokeWidth = 6f; strokeJoin = Paint.Join.ROUND; strokeCap = Paint.Cap.ROUND
        })
        c.drawCircle(x(values.size - 1), y(values.last()), 9f, Paint(Paint.ANTI_ALIAS_FLAG).apply { this.color = color })
        return bmp
    }
}

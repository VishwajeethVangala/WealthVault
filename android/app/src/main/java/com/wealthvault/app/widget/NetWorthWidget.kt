package com.wealthvault.app.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.widget.RemoteViews
import com.wealthvault.app.MainActivity
import com.wealthvault.app.R
import com.wealthvault.app.data.Api
import com.wealthvault.app.data.Prefs
import com.wealthvault.app.ui.dayPnlOf
import com.wealthvault.app.ui.plainMoney
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs

/**
 * The home screen widget: today's change in net worth, as a percentage. Amounts show only when the eye switch has them
 * on and the app lock is off, because a home screen can be seen without unlocking the phone or the app.
 *
 * It reads the holdings as last synced (no broker calls), keeps the last answer so a dropped connection still shows
 * something, and is refreshed by the system every half hour and whenever the app is left.
 */
class NetWorthWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val pending = goAsync()
        val app = context.applicationContext
        CoroutineScope(Dispatchers.IO).launch {
            try {
                refresh(app, manager, ids)
            } finally {
                pending.finish()
            }
        }
    }

    companion object {
        private const val CACHE = "wv_widget"

        /** Asks every placed widget to refresh itself (a no-op when none is placed). */
        fun requestUpdate(context: Context) {
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, NetWorthWidget::class.java))
            if (ids.isEmpty()) return
            context.sendBroadcast(
                Intent(context, NetWorthWidget::class.java)
                    .setAction(AppWidgetManager.ACTION_APPWIDGET_UPDATE)
                    .putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids),
            )
        }

        private suspend fun refresh(context: Context, manager: AppWidgetManager, ids: IntArray) {
            val prefs = Prefs(context)
            val session = prefs.current()
            val cache = context.getSharedPreferences(CACHE, Context.MODE_PRIVATE)
            if (session.token == null) {
                cache.edit().clear().apply() // nothing of a signed-out account stays on the home screen
                draw(context, manager, ids, null, showAmounts = false)
                return
            }
            val fresh = runCatching {
                val holdings = withTimeout(8_000) { Api(prefs).holdings(live = false) }
                val total = holdings.sumOf { it.current_value }
                val day = holdings.sumOf { dayPnlOf(it) ?: 0.0 }
                val prev = total - day
                Reading(total, day, if (prev > 0) day / prev * 100.0 else null, System.currentTimeMillis())
            }.getOrNull()
            if (fresh != null) {
                cache.edit().putFloat("total", fresh.total.toFloat()).putFloat("day", fresh.day.toFloat())
                    .putFloat("pct", fresh.pct?.toFloat() ?: Float.NaN).putLong("at", fresh.at).apply()
            }
            val reading = fresh ?: cache.takeIf { it.contains("at") }?.let {
                Reading(it.getFloat("total", 0f).toDouble(), it.getFloat("day", 0f).toDouble(), it.getFloat("pct", Float.NaN).toDouble().takeIf { p -> !p.isNaN() }, it.getLong("at", 0L))
            }
            draw(context, manager, ids, reading, showAmounts = !session.hideAmounts && !session.lock)
        }

        private data class Reading(val total: Double, val day: Double, val pct: Double?, val at: Long)

        private fun draw(context: Context, manager: AppWidgetManager, ids: IntArray, r: Reading?, showAmounts: Boolean) {
            val views = RemoteViews(context.packageName, R.layout.widget_networth)
            when {
                r == null -> {
                    views.setTextViewText(R.id.w_main, "Open WealthVault")
                    views.setTextColor(R.id.w_main, Color.rgb(0x5B, 0x6B, 0x7B))
                    views.setTextViewText(R.id.w_sub, "Sign in to see today's change")
                    views.setTextViewText(R.id.w_time, "")
                }
                r.pct == null -> {
                    views.setTextViewText(R.id.w_main, "No change yet")
                    views.setTextColor(R.id.w_main, Color.rgb(0x5B, 0x6B, 0x7B))
                    views.setTextViewText(R.id.w_sub, "Today")
                    views.setTextViewText(R.id.w_time, stamp(r.at))
                }
                else -> {
                    val up = r.pct >= 0
                    views.setTextViewText(R.id.w_main, "${if (up) "▲" else "▼"} ${String.format(Locale.US, "%.2f", abs(r.pct))}%")
                    views.setTextColor(R.id.w_main, if (up) Color.rgb(0x1E, 0x8E, 0x5A) else Color.rgb(0xC0, 0x39, 0x2B))
                    views.setTextViewText(R.id.w_sub, if (showAmounts) "${plainMoney(r.total, 0)} · ${if (r.day >= 0) "+" else ""}${plainMoney(r.day, 0)}" else "Net worth today")
                    views.setTextViewText(R.id.w_time, stamp(r.at))
                }
            }
            val open = PendingIntent.getActivity(
                context, 0,
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            views.setOnClickPendingIntent(R.id.w_root, open)
            ids.forEach { manager.updateAppWidget(it, views) }
        }

        private fun stamp(at: Long) = if (at <= 0) "" else "Updated " + SimpleDateFormat("h:mm a", Locale.getDefault()).format(Date(at))
    }
}

package com.wealthvault.app.ui

import android.content.Context
import android.os.Bundle
import com.google.firebase.analytics.FirebaseAnalytics
import com.google.firebase.crashlytics.FirebaseCrashlytics
import java.security.MessageDigest

/**
 * Usage analytics and crash reports (Firebase). Both stay off until the person says yes, and can be turned off
 * again in Settings. Events carry no amounts, holdings, emails or names; people are known only by a hashed id
 * (the same one the web app uses, so one person is one user across both).
 */
object Analytics {
    private var analytics: FirebaseAnalytics? = null
    private var crashes: FirebaseCrashlytics? = null

    @Volatile
    private var enabled = false

    /** Start-up: Firebase is created, but collection is off in the manifest until [apply] says otherwise. */
    fun attach(context: Context) {
        if (analytics != null) return
        analytics = FirebaseAnalytics.getInstance(context.applicationContext)
        crashes = FirebaseCrashlytics.getInstance()
    }

    /** Turns collection on or off to match the person's choice. */
    fun apply(granted: Boolean) {
        enabled = granted
        analytics?.setAnalyticsCollectionEnabled(granted)
        crashes?.isCrashlyticsCollectionEnabled = granted
    }

    fun identify(userId: String?) {
        analytics?.setUserId(userId?.takeIf { it.isNotBlank() }?.let { hash("wv:$it") })
    }

    fun log(event: String, vararg params: Pair<String, Any?>) {
        if (!enabled) return
        val bundle = Bundle().apply {
            putString("platform", "android")
            params.forEach { (k, v) ->
                when (v) {
                    null -> Unit
                    is Int -> putLong(k, v.toLong())
                    is Long -> putLong(k, v)
                    is Boolean -> putString(k, v.toString())
                    else -> putString(k, v.toString().take(100))
                }
            }
        }
        analytics?.logEvent(event, bundle)
    }

    private val SCREENS = mapOf(
        "overview" to "overview", "holdings" to "holdings", "signals" to "signals", "momentum" to "momentum",
        "strategy" to "ath_strategy", "brokers" to "brokers", "settings" to "settings", "feedback" to "feedback",
    )

    fun screen(route: String?) = log("screen_view", "screen_name" to (SCREENS[route] ?: "other"))

    /** Names the screens use for the `page` of a search event. */
    fun pageOf(route: String?) = SCREENS[route] ?: "other"

    /**
     * What a person typed into a search box, made safe to send: upper-cased, cut to 100 characters, and dropped
     * altogether when it looks like an email address or a long number.
     */
    fun cleanSearchTerm(raw: String): String? {
        val t = raw.trim().replace(Regex("\\s+"), " ").uppercase().take(100)
        if (t.length < 2) return null
        if ('@' in t || Regex("\\d{6,}").containsMatchIn(t.replace(Regex("[\\s-]"), ""))) return null
        return t
    }

    private fun hash(text: String): String =
        MessageDigest.getInstance("SHA-256").digest(text.toByteArray()).joinToString("") { "%02x".format(it) }.take(32)
}

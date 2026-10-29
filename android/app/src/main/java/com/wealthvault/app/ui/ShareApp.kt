package com.wealthvault.app.ui

import android.content.Context
import android.content.Intent

/**
 * "Share WealthVault": the phone's own share sheet (WhatsApp, Messages, email and the rest) with a short message and
 * the Play Store link. The same message is on the web (web/src/utils/share.ts). Nothing about the person's portfolio
 * is ever in it. The link carries a campaign tag so installs that came from a share can be counted.
 */
object ShareApp {
    private const val PLAY_LINK =
        "https://play.google.com/store/apps/details?id=com.vangala.wealthvault&referrer=utm_source%3Dwealthvault_share%26utm_medium%3Dandroid_app"

    val message = "I keep all my stocks, mutual funds and NPS in one place with WealthVault. It reads holdings from my brokers, " +
        "locks behind my fingerprint, and never shows amounts on the lock screen.\n" +
        "Android: $PLAY_LINK\n" +
        "iOS coming soon."

    fun open(context: Context, from: String) {
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, message)
            putExtra(Intent.EXTRA_SUBJECT, "WealthVault: all your investments in one place")
        }
        context.startActivity(Intent.createChooser(send, "Share WealthVault").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        Analytics.log("share_app", "from" to from)
    }
}

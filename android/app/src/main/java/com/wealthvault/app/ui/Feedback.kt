package com.wealthvault.app.ui

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.google.android.play.core.review.ReviewManagerFactory
import com.wealthvault.app.BuildConfig

/** Opens a link in whatever app handles it; says so instead of crashing when nothing on the phone can. */
fun openLink(context: Context, url: String) {
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    } catch (e: ActivityNotFoundException) {
        android.widget.Toast.makeText(context, "No app on this phone can open $url", android.widget.Toast.LENGTH_LONG).show()
    }
}

/** Opens WealthVault's page on Google Play (the store app if there is one, else the website). */
fun openPlayListing(context: Context) {
    val id = context.packageName
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$id")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    } catch (e: ActivityNotFoundException) {
        openLink(context, "https://play.google.com/store/apps/details?id=$id")
    }
}

/** How many openings before the first review prompt, and between prompts after that. */
private const val FIRST_ASK_AT = 5
private const val ASK_EVERY = 30

/**
 * Asks for a Play Store review after a few openings, in Google's own in-app dialog. Google decides whether the
 * dialog actually shows (it limits how often a person sees it), so the "Rate WealthVault" link in the profile menu stays
 * as the way to rate at any time.
 */
suspend fun maybeAskForReview(activity: Activity, vm: AppViewModel) {
    val opens = vm.prefs.opens()
    val asked = vm.prefs.reviewAskedAt()
    if (opens < FIRST_ASK_AT || (asked > 0 && opens - asked < ASK_EVERY)) return
    vm.prefs.markReviewAsked(opens)
    val manager = ReviewManagerFactory.create(activity)
    manager.requestReviewFlow().addOnCompleteListener { task ->
        if (task.isSuccessful && !activity.isFinishing) manager.launchReviewFlow(activity, task.result)
    }
}

private val CATEGORIES = listOf("idea" to "Idea", "problem" to "Problem", "praise" to "Praise", "other" to "Other")
private const val MAX_MESSAGE = 2000

@Composable
fun FeedbackScreen(vm: AppViewModel) {
    val sending by vm.feedbackSending.collectAsState()
    val result by vm.feedbackResult.collectAsState()
    val supportEmail by vm.supportEmail.collectAsState()
    var category by rememberSaveable { mutableStateOf("idea") }
    var message by rememberSaveable { mutableStateOf("") }
    val context = LocalContext.current
    LaunchedEffect(Unit) { vm.feedbackResult.value = null; vm.loadSupportEmail() }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { PageTitle("Send feedback", "An idea, a problem or anything else. It goes straight to the people who build WealthVault.") }
        val sent = result?.first == true
        if (sent) {
            item {
                WvCard {
                    Text("Thank you, it's received.", style = Wv.title, color = Wv.c.gain)
                    Text("We read every message. If a reply is needed, it comes to the email you signed in with.", style = Wv.sub, color = Wv.c.text2)
                    OutlinedButton(onClick = { message = ""; vm.feedbackResult.value = null }, shape = RoundedCornerShape(10.dp)) { Text("Send another", color = Wv.c.text) }
                }
            }
        } else {
            item {
                WvCard {
                    Label("What is it about?")
                    Row(Modifier.padding(top = 4.dp).horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        CATEGORIES.forEach { (k, label) -> Chip(label, category == k) { category = k } }
                    }
                    OutlinedTextField(
                        message, { message = it.take(MAX_MESSAGE) },
                        label = { Text("Your message") },
                        placeholder = { Text(if (category == "problem") "What happened, and on which page?" else "Tell us what you think") },
                        supportingText = { Text("${message.length} / $MAX_MESSAGE") },
                        modifier = Modifier.fillMaxWidth().heightIn(min = 140.dp),
                    )
                    Text("Sent with the app version (${BuildConfig.VERSION_NAME}) and your sign-in email, so we can reply. Nothing about your holdings is included.", style = Wv.small, color = Wv.c.text3)
                    result?.takeIf { !it.first }?.let { Note(it.second, bad = true) }
                    PrimaryButton(if (sending) "Sending…" else "Send", busy = sending, enabled = message.isNotBlank(), modifier = Modifier.fillMaxWidth()) {
                        vm.sendFeedback(category, message)
                    }
                }
            }
        }
        item {
            WvCard {
                Label("Other ways")
                Text("Enjoying WealthVault? A rating on Google Play helps others find it.", style = Wv.sub, color = Wv.c.text2)
                OutlinedButton(onClick = { openPlayListing(context) }, shape = RoundedCornerShape(10.dp)) { Text("Rate on Google Play", color = Wv.c.accent) }
                if (supportEmail.isNotBlank()) {
                    TextButton(onClick = {
                        val mail = Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:$supportEmail")).putExtra(Intent.EXTRA_SUBJECT, "WealthVault ${BuildConfig.VERSION_NAME}")
                        runCatching { context.startActivity(mail) }
                    }) { Text("Email $supportEmail", color = Wv.c.text2) }
                }
            }
        }
    }
}

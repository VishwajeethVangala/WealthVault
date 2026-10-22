package com.wealthvault.app.ui

import android.app.Application
import android.content.Context
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.wealthvault.app.data.Api
import com.wealthvault.app.data.BrokerSession
import com.wealthvault.app.data.Holding
import com.wealthvault.app.data.Prefs
import com.wealthvault.app.data.Session
import com.wealthvault.app.data.Summary
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** Something loaded from the server: still loading, here, or failed with words to show. */
data class Load<T>(val loading: Boolean = false, val data: T? = null, val error: String? = null)

class AppViewModel(app: Application) : AndroidViewModel(app) {
    val prefs = Prefs(app)
    private val api = Api(prefs)

    val session: StateFlow<Session?> = prefs.session.stateIn(viewModelScope, SharingStarted.Eagerly, null)

    val summary = MutableStateFlow(Load<Summary?>())
    val holdings = MutableStateFlow(Load<List<Holding>>())
    val brokers = MutableStateFlow(Load<List<BrokerSession>>())
    val syncing = MutableStateFlow<String?>(null) // "all", a connection id, or null
    val message = MutableStateFlow<String?>(null)
    /** A neutral note for the sign-in screen, such as "your account was deleted". */
    val notice = MutableStateFlow<String?>(null)
    val signingIn = MutableStateFlow(false)

    /** The broker and asset-class filters, shared by the Overview and Holdings (the web keeps them in the URL). */
    val brokerFilter = MutableStateFlow<Set<String>>(emptySet())
    val classFilter = MutableStateFlow<Set<String>>(emptySet())

    fun setHideAmounts(on: Boolean) = viewModelScope.launch { prefs.saveHideAmounts(on) }

    // --- the feedback form ---
    val feedbackSending = MutableStateFlow(false)
    /** (sent, message): true once received; false with the reason when it failed */
    val feedbackResult = MutableStateFlow<Pair<Boolean, String>?>(null)
    val supportEmail = MutableStateFlow("")

    fun sendFeedback(category: String, message: String) {
        if (feedbackSending.value || message.isBlank()) return
        feedbackSending.value = true
        viewModelScope.launch {
            feedbackResult.value = try {
                api.sendFeedback(category, message.trim(), com.wealthvault.app.BuildConfig.VERSION_NAME)
                true to "Received"
            } catch (e: Exception) {
                false to (e.message ?: "Could not send. Please try again.")
            } finally {
                feedbackSending.value = false
            }
        }
    }

    fun loadSupportEmail() = viewModelScope.launch {
        runCatching { api.authConfig() }.getOrNull()?.let { supportEmail.value = it.support_email }
    }

    private fun <T> load(target: MutableStateFlow<Load<T>>, block: suspend () -> T) {
        target.value = target.value.copy(loading = true, error = null)
        viewModelScope.launch {
            target.value = try {
                Load(data = block())
            } catch (e: Exception) {
                Load(data = target.value.data, error = e.message ?: "Something went wrong.")
            }
        }
    }

    fun refreshAll() {
        load(summary) { api.summary() }
        loadHoldings()
        load(brokers) { api.sessions() }
    }

    /** The saved holdings first so screens fill at once, then the same list on live prices. */
    private fun loadHoldings() {
        holdings.value = holdings.value.copy(loading = true, error = null)
        viewModelScope.launch {
            if (holdings.value.data == null) {
                runCatching { api.holdings(live = false) }.getOrNull()?.let { holdings.value = Load(loading = true, data = it) }
            }
            holdings.value = try {
                Load(data = api.holdings(live = true))
            } catch (e: Exception) {
                Load(data = holdings.value.data, error = if (holdings.value.data == null) e.message ?: "Could not load holdings." else null)
            }
        }
    }

    fun loadBrokers() = load(brokers) { api.sessions() }

    private fun shortName(b: BrokerSession) = b.display_name.substringBefore(" — ").ifBlank { b.broker_name }

    /** What went wrong with one broker's sync, or null when it synced. */
    private fun problemOf(b: BrokerSession): String? = when {
        b.status == "CONNECTED" -> null
        b.status == "AUTH_REQUIRED" || b.status == "SESSION_EXPIRED" -> "${shortName(b)} needs a login"
        else -> "${shortName(b)} could not sync"
    }

    /**
     * Sync all runs each broker's own sync, one after another (each rewrites the stored holdings, so not in parallel),
     * so it behaves exactly like Sync now on a broker card and says which brokers need a login or failed.
     */
    fun syncAll() {
        if (syncing.value != null) return
        syncing.value = "all"
        message.value = null
        viewModelScope.launch {
            try {
                val list = api.sessions()
                val problems = mutableListOf<String>()
                var ok = 0
                list.forEach { b ->
                    try {
                        val updated = api.syncOne(b.connection_id)
                        val p = problemOf(updated)
                        if (p == null) ok++ else problems += p
                    } catch (e: Exception) {
                        problems += "${shortName(b)} failed"
                    }
                }
                message.value = when {
                    list.isEmpty() -> "No brokers linked yet. Add one on the Brokers page."
                    problems.isEmpty() -> "Synced" + if (list.size > 1) " all ${list.size} brokers. Holdings and the overview are up to date." else ". Holdings and the overview are up to date."
                    else -> "Synced $ok of ${list.size} · ${problems.joinToString(", ")}"
                }
            } catch (e: Exception) {
                message.value = e.message ?: "Sync failed."
            } finally {
                syncing.value = null
                refreshAll()
            }
        }
    }

    fun syncOne(connectionId: String) {
        if (syncing.value != null) return
        syncing.value = connectionId
        message.value = null
        viewModelScope.launch {
            try {
                val updated = api.syncOne(connectionId)
                message.value = problemOf(updated)?.let { p -> updated.error_message?.takeIf { it.isNotBlank() } ?: p }
            } catch (e: Exception) {
                message.value = e.message
            } finally {
                syncing.value = null
                refreshAll()
            }
        }
    }

    fun saveBaseUrl(url: String) = viewModelScope.launch { prefs.saveBaseUrl(url) }

    /** Whether the app lock has been passed since the app was opened or came back to the front. */
    val unlocked = MutableStateFlow(false)

    fun setLock(on: Boolean) = viewModelScope.launch {
        prefs.saveLock(on)
        unlocked.value = true // the person has just proved who they are
    }

    val deleting = MutableStateFlow(false)

    /** Deletes the account and all its data on the server, then signs out here. */
    fun deleteAccount() {
        if (deleting.value) return
        deleting.value = true
        message.value = null
        viewModelScope.launch {
            try {
                api.deleteAccount()
                prefs.signOut()
                prefs.saveLock(false)
                summary.value = Load(); holdings.value = Load(); brokers.value = Load()
                notice.value = "Your account and all its data were deleted."
            } catch (e: Exception) {
                message.value = e.message ?: "Could not delete the account."
            } finally {
                deleting.value = false
            }
        }
    }

    fun setTheme(value: String) = viewModelScope.launch { prefs.saveTheme(value) }

    /** Debug builds only (see MainActivity): sign in with a token issued by a test server. */
    fun debugSignIn(baseUrl: String, token: String) = viewModelScope.launch {
        prefs.saveDebugBaseUrl(baseUrl)
        prefs.signIn(com.wealthvault.app.data.TokenResponse(token, com.wealthvault.app.data.User("test", "test@local", "Test")))
    }

    /** Username-and-password sign-in for the sample account (store reviewers cannot use Google sign-in). */
    fun signInDemo(username: String, password: String) {
        if (signingIn.value) return
        signingIn.value = true
        message.value = null
        viewModelScope.launch {
            try {
                prefs.signIn(api.signInDemo(username, password))
            } catch (e: Exception) {
                message.value = if (e.message?.contains("401") == true) "Wrong username or password." else (e.message ?: "Sign-in failed.")
            } finally {
                signingIn.value = false
            }
        }
    }

    fun signOut() = viewModelScope.launch {
        prefs.signOut()
        summary.value = Load()
        holdings.value = Load()
        brokers.value = Load()
    }

    /**
     * Google sign-in with Android's Credential Manager. The Google client ID comes from the server
     * (/auth/config), so the ID token is checked against the same client the web app uses.
     */
    fun signIn(activityContext: Context) {
        if (signingIn.value) return
        signingIn.value = true
        message.value = null
        viewModelScope.launch {
            try {
                val clientId = api.authConfig().google_client_id
                if (clientId.isBlank()) throw IllegalStateException("The server has no Google sign-in set up.")
                val request = GetCredentialRequest.Builder().addCredentialOption(GetSignInWithGoogleOption.Builder(clientId).build()).build()
                val result = CredentialManager.create(activityContext).getCredential(activityContext, request)
                val cred = result.credential
                if (cred is CustomCredential && cred.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
                    val idToken = GoogleIdTokenCredential.createFrom(cred.data).idToken
                    prefs.signIn(api.signInWithGoogle(idToken)) // the signed-in screen loads everything
                } else {
                    message.value = "That sign-in type is not supported. Use a Google account."
                }
            } catch (e: GetCredentialCancellationException) {
                // Also what Google returns when it does not know this app yet (no Android OAuth client).
                message.value = "Sign-in closed. If you picked an account and it closed by itself, Google does not recognise this app yet (see the setup step in the README)."
            } catch (e: NoCredentialException) {
                message.value = "No Google account to sign in with. Add one to the phone, or (first install) finish the Google setup in the app's README."
            } catch (e: GetCredentialException) {
                message.value = "Google sign-in did not finish: ${e.message ?: e.type}"
            } catch (e: Exception) {
                message.value = e.message ?: "Sign-in failed."
            } finally {
                signingIn.value = false
            }
        }
    }
}

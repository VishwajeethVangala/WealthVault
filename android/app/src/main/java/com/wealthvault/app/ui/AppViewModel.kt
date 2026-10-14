package com.wealthvault.app.ui

import android.app.Application
import android.content.Context
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
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
    val signingIn = MutableStateFlow(false)

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
        load(holdings) { api.holdings() }
        load(brokers) { api.sessions() }
    }

    fun loadBrokers() = load(brokers) { api.sessions() }

    fun syncAll() {
        if (syncing.value != null) return
        syncing.value = "all"
        viewModelScope.launch {
            try {
                api.syncAll()
                message.value = "Synced. Holdings and the overview are up to date."
            } catch (e: Exception) {
                message.value = e.message
            } finally {
                syncing.value = null
                refreshAll()
            }
        }
    }

    fun syncOne(connectionId: String) {
        if (syncing.value != null) return
        syncing.value = connectionId
        viewModelScope.launch {
            try {
                api.syncOne(connectionId)
            } catch (e: Exception) {
                message.value = e.message
            } finally {
                syncing.value = null
                refreshAll()
            }
        }
    }

    fun saveBaseUrl(url: String) = viewModelScope.launch { prefs.saveBaseUrl(url) }

    fun setTheme(value: String) = viewModelScope.launch { prefs.saveTheme(value) }

    /** Debug builds only (see MainActivity): sign in with a token issued by a test server. */
    fun debugSignIn(baseUrl: String, token: String) = viewModelScope.launch {
        prefs.saveBaseUrl(baseUrl)
        prefs.signIn(com.wealthvault.app.data.TokenResponse(token, com.wealthvault.app.data.User("test", "test@local", "Test")))
        refreshAll()
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
                    prefs.signIn(api.signInWithGoogle(idToken))
                    refreshAll()
                } else {
                    message.value = "That sign-in type is not supported. Use a Google account."
                }
            } catch (e: GetCredentialCancellationException) {
                // the person closed the account picker
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

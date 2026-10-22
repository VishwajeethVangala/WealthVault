package com.wealthvault.app.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.wealthvault.app.BuildConfig
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.store by preferencesDataStore("wealthvault")

/** What the app keeps on the phone: the server address, the sign-in token, who is signed in, and the theme. */
data class Session(val baseUrl: String, val token: String?, val name: String, val email: String, val theme: String, val lock: Boolean = false, val hideAmounts: Boolean = true)

class Prefs(private val context: Context) {
    private val baseUrl = stringPreferencesKey("base_url")
    private val debugBaseUrl = stringPreferencesKey("debug_base_url") // set only by the debug test hook
    private val token = stringPreferencesKey("token")
    private val name = stringPreferencesKey("name")
    private val email = stringPreferencesKey("email")
    private val theme = stringPreferencesKey("theme") // system | light | dark
    private val lock = booleanPreferencesKey("app_lock") // ask for fingerprint / face / screen lock on opening
    private val hideAmounts = booleanPreferencesKey("hide_amounts") // the eye switch
    private val opens = intPreferencesKey("opens") // app openings, for the review prompt
    private val reviewAskedAt = intPreferencesKey("review_asked_at") // the opening count when the review was last offered

    val session: Flow<Session> = context.store.data.map {
        Session(
            // built-in address first; a typed one only when the build has none
            baseUrl = it[debugBaseUrl] ?: BuildConfig.DEFAULT_BASE_URL.ifBlank { it[baseUrl] ?: "" },
            token = it[token],
            name = it[name] ?: "",
            email = it[email] ?: "",
            theme = it[theme] ?: "system",
            lock = it[lock] ?: false,
            // amounts start hidden; they show only once switched on with the eye button
            hideAmounts = it[hideAmounts] ?: true,
        )
    }

    suspend fun current(): Session = session.first()

    suspend fun saveBaseUrl(url: String) {
        context.store.edit { it[baseUrl] = url.trim().trimEnd('/') }
    }

    suspend fun saveDebugBaseUrl(url: String) {
        context.store.edit { it[debugBaseUrl] = url.trim().trimEnd('/') }
    }

    suspend fun signIn(t: TokenResponse) {
        context.store.edit {
            it[token] = t.access_token
            it[name] = t.user.name
            it[email] = t.user.email
        }
    }

    suspend fun signOut() {
        context.store.edit {
            it.remove(token)
            it.remove(name)
            it.remove(email)
        }
    }

    suspend fun saveLock(on: Boolean) {
        context.store.edit { it[lock] = on }
    }

    suspend fun saveHideAmounts(on: Boolean) {
        context.store.edit { it[hideAmounts] = on }
    }

    /** Counts this opening and returns the new count. */
    suspend fun countOpen(): Int {
        var n = 0
        context.store.edit { n = (it[opens] ?: 0) + 1; it[opens] = n }
        return n
    }

    suspend fun reviewAskedAt(): Int = context.store.data.first()[reviewAskedAt] ?: 0

    suspend fun opens(): Int = context.store.data.first()[opens] ?: 0

    suspend fun markReviewAsked(atOpen: Int) {
        context.store.edit { it[reviewAskedAt] = atOpen }
    }

    suspend fun saveTheme(value: String) {
        context.store.edit { it[theme] = value }
    }
}

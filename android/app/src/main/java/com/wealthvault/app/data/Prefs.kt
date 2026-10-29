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
data class Session(val baseUrl: String, val token: String?, val name: String, val email: String, val theme: String, val lock: Boolean = false, val hideAmounts: Boolean = true, val demo: Boolean = false,
                   /** "granted" or "denied"; null until the person has been asked about usage analytics */
                   val analytics: String? = null, val userId: String = "", val notifAsked: Boolean = false)

class Prefs(private val context: Context) {
    private val baseUrl = stringPreferencesKey("base_url")
    private val debugBaseUrl = stringPreferencesKey("debug_base_url") // set only by the debug test hook
    private val token = stringPreferencesKey("token")
    private val name = stringPreferencesKey("name")
    private val email = stringPreferencesKey("email")
    private val theme = stringPreferencesKey("theme") // system | light | dark
    private val lock = booleanPreferencesKey("app_lock") // ask for fingerprint / face / screen lock on opening
    private val hideAmounts = booleanPreferencesKey("hide_amounts") // the eye switch
    private val analytics = stringPreferencesKey("analytics_consent") // granted | denied
    private val userId = stringPreferencesKey("user_id")
    private val notifAsked = booleanPreferencesKey("notifications_asked") // the phone has been asked about showing notifications
    private val fcmToken = stringPreferencesKey("fcm_token") // this phone's push address, kept so sign-out can forget it
    private val demo = booleanPreferencesKey("demo_account") // signed in with the store reviewers' sample account
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
            demo = it[demo] ?: false,
            analytics = it[analytics],
            userId = it[userId] ?: "",
            notifAsked = it[notifAsked] ?: false,
        )
    }

    suspend fun current(): Session = session.first()

    suspend fun saveBaseUrl(url: String) {
        context.store.edit { it[baseUrl] = url.trim().trimEnd('/') }
    }

    suspend fun saveDebugBaseUrl(url: String) {
        context.store.edit { it[debugBaseUrl] = url.trim().trimEnd('/') }
    }

    suspend fun signIn(t: TokenResponse, demoAccount: Boolean = false) {
        context.store.edit {
            it[token] = t.access_token
            it[demo] = demoAccount
            it[userId] = t.user.user_id
            it[name] = t.user.name
            it[email] = t.user.email
        }
    }

    suspend fun signOut() {
        context.store.edit {
            it.remove(token)
            it.remove(name)
            it.remove(email)
            it.remove(demo)
            it.remove(userId)
        }
    }

    suspend fun saveNotifAsked() {
        context.store.edit { it[notifAsked] = true }
    }

    suspend fun fcmToken(): String? = context.store.data.first()[fcmToken]

    suspend fun saveFcmToken(token: String?) {
        context.store.edit { if (token == null) it.remove(fcmToken) else it[fcmToken] = token }
    }

    suspend fun saveAnalytics(on: Boolean) {
        context.store.edit { it[analytics] = if (on) "granted" else "denied" }
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

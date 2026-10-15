package com.wealthvault.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.wealthvault.app.BuildConfig
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.store by preferencesDataStore("wealthvault")

/** What the app keeps on the phone: the server address, the sign-in token, who is signed in, and the theme. */
data class Session(val baseUrl: String, val token: String?, val name: String, val email: String, val theme: String)

class Prefs(private val context: Context) {
    private val baseUrl = stringPreferencesKey("base_url")
    private val debugBaseUrl = stringPreferencesKey("debug_base_url") // set only by the debug test hook
    private val token = stringPreferencesKey("token")
    private val name = stringPreferencesKey("name")
    private val email = stringPreferencesKey("email")
    private val theme = stringPreferencesKey("theme") // system | light | dark

    val session: Flow<Session> = context.store.data.map {
        Session(
            // built-in address first; a typed one only when the build has none
            baseUrl = it[debugBaseUrl] ?: BuildConfig.DEFAULT_BASE_URL.ifBlank { it[baseUrl] ?: "" },
            token = it[token],
            name = it[name] ?: "",
            email = it[email] ?: "",
            theme = it[theme] ?: "system",
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

    suspend fun saveTheme(value: String) {
        context.store.edit { it[theme] = value }
    }
}

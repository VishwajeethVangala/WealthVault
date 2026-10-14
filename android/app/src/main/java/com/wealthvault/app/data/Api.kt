package com.wealthvault.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/** A refused request, with the server's own words when it sent them (FastAPI `detail`). */
class ApiException(val code: Int, message: String) : Exception(message)

/** Calls the WealthVault server: the same endpoints, data and broker connections as the web app. */
class Api(private val prefs: Prefs) {
    private val http = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(180, TimeUnit.SECONDS) // a full broker sync can take a while
        .build()
    private val json = Json { ignoreUnknownKeys = true; coerceInputValues = true; explicitNulls = false }
    private val jsonType = "application/json".toMediaType()

    private suspend fun call(method: String, path: String, body: String? = null, auth: Boolean = true): String = withContext(Dispatchers.IO) {
        val s = prefs.current()
        if (s.baseUrl.isBlank()) throw ApiException(0, "Set the server address first.")
        val builder = Request.Builder().url(s.baseUrl + "/api/v1" + path)
        if (auth) s.token?.let { builder.header("Authorization", "Bearer $it") }
        if (method != "GET") builder.method(method, (body ?: "").toRequestBody(jsonType))
        val text: String
        val code: Int
        try {
            http.newCall(builder.build()).execute().use { r ->
                text = r.body?.string().orEmpty()
                code = r.code
            }
        } catch (e: IOException) {
            throw ApiException(0, "Can't reach the server. Check the internet connection and the server address.")
        }
        if (code !in 200..299) {
            if (code == 401 && auth) prefs.signOut()
            val detail = runCatching { (json.parseToJsonElement(text) as JsonObject)["detail"] as? JsonPrimitive }.getOrNull()
            throw ApiException(code, detail?.content ?: if (code == 401) "Please sign in again." else "The server could not do that ($code).")
        }
        text
    }

    suspend fun authConfig(): AuthConfig = json.decodeFromString(call("GET", "/auth/config", auth = false))

    suspend fun signInWithGoogle(idToken: String): TokenResponse {
        val body = buildJsonObject { put("credential", idToken) }.toString()
        return json.decodeFromString(call("POST", "/auth/google", body, auth = false))
    }

    /** The latest portfolio snapshot, or null before the first sync. */
    suspend fun summary(): Summary? = try {
        json.decodeFromString<Summary>(call("GET", "/portfolio/summary"))
    } catch (e: ApiException) {
        if (e.code == 404) null else throw e
    }

    suspend fun holdings(): List<Holding> = json.decodeFromString(call("GET", "/portfolio/holdings?refresh_live=true"))

    suspend fun sessions(): List<BrokerSession> = json.decodeFromString(call("GET", "/portfolio/sessions"))

    suspend fun syncAll() {
        call("POST", "/portfolio/sync")
    }

    suspend fun syncOne(connectionId: String): BrokerSession =
        json.decodeFromString(call("POST", "/portfolio/sessions/${URLEncoder.encode(connectionId, "UTF-8")}/sync"))
}

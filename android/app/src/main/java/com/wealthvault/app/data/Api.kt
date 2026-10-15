package com.wealthvault.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.putJsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/**
 * A refused request, with the server's own words when it sent them (FastAPI `detail`). [authUrl] is set when
 * the server needs a broker login first (for example today's Kite login for price history).
 */
class ApiException(val code: Int, message: String, val authUrl: String? = null) : Exception(message)

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
        var text = ""
        var code = 0
        // a read can fail on a dropped mobile connection; try a GET once more before giving up
        var attempt = 0
        while (true) {
            try {
                http.newCall(builder.build()).execute().use { r ->
                    text = r.body?.string().orEmpty()
                    code = r.code
                }
                break
            } catch (e: IOException) {
                if (method != "GET" || ++attempt > 1) throw ApiException(0, "Can't reach the server. Check the internet connection and the server address.")
            }
        }
        if (code !in 200..299) {
            if (code == 401 && auth) prefs.signOut()
            val detail = runCatching { (json.parseToJsonElement(text) as JsonObject)["detail"] }.getOrNull()
            val fallback = if (code == 401) "Please sign in again." else "The server could not do that ($code)."
            when (detail) {
                is JsonPrimitive -> throw ApiException(code, detail.content)
                is JsonObject -> throw ApiException(
                    code,
                    (detail["message"] as? JsonPrimitive)?.content ?: fallback,
                    (detail["auth_url"] as? JsonPrimitive)?.contentOrNull,
                )
                else -> throw ApiException(code, fallback)
            }
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

    /** Holdings as last synced; with [live], prices are refreshed from the brokers first (slower). */
    suspend fun holdings(live: Boolean = true): List<Holding> =
        json.decodeFromString(call("GET", "/portfolio/holdings" + if (live) "?refresh_live=true" else ""))

    suspend fun sessions(): List<BrokerSession> = json.decodeFromString(call("GET", "/portfolio/sessions"))

    suspend fun syncAll() {
        call("POST", "/portfolio/sync")
    }

    suspend fun syncOne(connectionId: String): BrokerSession =
        json.decodeFromString(call("POST", "/portfolio/sessions/${URLEncoder.encode(connectionId, "UTF-8")}/sync"))

    private fun enc(v: String) = URLEncoder.encode(v, "UTF-8")

    // --- equity signals and Stage 2 -----------------------------------------------------------------------

    suspend fun signals(market: String): SignalsResponse = json.decodeFromString(call("GET", "/analytics/signals?market=$market"))

    suspend fun liveSignals(market: String): LiveSignalsResponse = json.decodeFromString(call("GET", "/analytics/signals/live?market=$market"))

    suspend fun refreshSignals(market: String) {
        call("POST", "/analytics/signals/refresh?market=$market")
    }

    suspend fun usLive(): UsLiveResponse = json.decodeFromString(call("GET", "/analytics/signals/us-live"))

    suspend fun stage2(): Stage2Response = json.decodeFromString(call("GET", "/analytics/stage2"))

    suspend fun stage2Live(): Stage2LiveResponse = json.decodeFromString(call("GET", "/analytics/stage2/live"))

    suspend fun stage2LiveSignals(): LiveSignalsResponse = json.decodeFromString(call("GET", "/analytics/stage2/live-signals"))

    suspend fun refreshStage2() {
        call("POST", "/analytics/stage2/refresh")
    }

    // --- one stock: momentum and strategy backtests (price history comes from Kite) ------------------------

    suspend fun momentum(symbol: String): MomentumAnalysis = json.decodeFromString(call("GET", "/analytics/momentum?symbol=${enc(symbol)}"))

    suspend fun swingStrategy(symbol: String): StrategyResult = json.decodeFromString(call("GET", "/analytics/strategy/swing-v21?symbol=${enc(symbol)}"))

    suspend fun athStrategy(symbol: String): StrategyResult = json.decodeFromString(call("GET", "/analytics/strategy/ath-breakout?symbol=${enc(symbol)}"))

    // --- brokers -------------------------------------------------------------------------------------------

    suspend fun brokerCatalog(): List<BrokerCatalogItem> = json.decodeFromString(call("GET", "/portfolio/brokers/catalog"))

    suspend fun addConnection(brokerName: String, label: String?): BrokerSession {
        val body = buildJsonObject {
            put("broker_name", brokerName)
            if (!label.isNullOrBlank()) put("account_label", label)
        }.toString()
        return json.decodeFromString(call("POST", "/portfolio/connections", body))
    }

    suspend fun saveCredentials(connectionId: String, fields: Map<String, String>): CredentialSaveResponse {
        val body = buildJsonObject { putJsonObject("fields") { fields.forEach { (k, v) -> put(k, v) } } }.toString()
        return json.decodeFromString(call("PUT", "/portfolio/connections/${enc(connectionId)}/credentials", body))
    }

    suspend fun deleteConnection(connectionId: String) {
        call("DELETE", "/portfolio/connections/${enc(connectionId)}?wipe_blobs=true")
    }

    // --- overview panels -----------------------------------------------------------------------------------

    suspend fun history(days: Int = 365): List<HistoryPoint> = json.decodeFromString(call("GET", "/portfolio/history?days=$days"))

    suspend fun targets(): Targets = json.decodeFromString(call("GET", "/portfolio/targets"))

    suspend fun saveTargets(targets: Map<String, Double>): Targets {
        val body = buildJsonObject { putJsonObject("targets") { targets.forEach { (k, v) -> put(k, v) } } }.toString()
        return json.decodeFromString(call("PUT", "/portfolio/targets", body))
    }

    suspend fun risk(): RiskResponse = json.decodeFromString(call("GET", "/analytics/signals/risk"))
}

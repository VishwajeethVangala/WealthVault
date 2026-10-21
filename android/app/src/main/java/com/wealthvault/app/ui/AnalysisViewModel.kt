package com.wealthvault.app.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.wealthvault.app.data.Api
import com.wealthvault.app.data.ApiException
import com.wealthvault.app.data.BrokerCatalogItem
import com.wealthvault.app.data.BrokerSession
import com.wealthvault.app.data.CredentialSaveResponse
import com.wealthvault.app.data.HistoryPoint
import com.wealthvault.app.data.LiveQuote
import com.wealthvault.app.data.MomentumAnalysis
import com.wealthvault.app.data.Prefs
import com.wealthvault.app.data.RiskResponse
import com.wealthvault.app.data.SignalsResponse
import com.wealthvault.app.data.Stage2Response
import com.wealthvault.app.data.StockSignals
import com.wealthvault.app.data.StrategyResult
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.time.DayOfWeek
import java.time.ZoneId
import java.time.ZonedDateTime

/** A failed load, with the broker login link when the server needs one (Kite's daily login). */
data class Problem(val text: String, val authUrl: String? = null)

/** Something loaded for one of the analysis screens. */
data class Res<T>(val loading: Boolean = false, val data: T? = null, val problem: Problem? = null)

private fun Exception.problem() = Problem(message ?: "Something went wrong.", (this as? ApiException)?.authUrl)

/** NSE cash session, Mon-Fri 09:15-15:30 IST. */
fun indiaSessionOpen(): Boolean {
    val t = ZonedDateTime.now(ZoneId.of("Asia/Kolkata"))
    val mins = t.hour * 60 + t.minute
    return t.dayOfWeek != DayOfWeek.SATURDAY && t.dayOfWeek != DayOfWeek.SUNDAY && mins in (9 * 60 + 15)..(15 * 60 + 30)
}

/** US regular session, Mon-Fri 09:30-16:00 New York time. */
fun usSessionOpen(): Boolean {
    val t = ZonedDateTime.now(ZoneId.of("America/New_York"))
    val mins = t.hour * 60 + t.minute
    return t.dayOfWeek != DayOfWeek.SATURDAY && t.dayOfWeek != DayOfWeek.SUNDAY && mins in (9 * 60 + 30)..(16 * 60)
}

/**
 * State for Equity signals, Stage 2, Momentum, Strategies, broker set-up and the extra Overview panels. It reads
 * the same endpoints as the web app; prices and signals are rebuilt on the live price while a session is open.
 */
class AnalysisViewModel(app: Application) : AndroidViewModel(app) {
    private val api = Api(Prefs(app))

    private fun <T> run(target: MutableStateFlow<Res<T>>, keep: Boolean = true, block: suspend () -> T) = viewModelScope.launch {
        target.value = Res(loading = true, data = if (keep) target.value.data else null)
        target.value = try {
            Res(data = block())
        } catch (e: Exception) {
            Res(data = if (keep) target.value.data else null, problem = e.problem())
        }
    }

    // --- equity signals ----------------------------------------------------------------------------------

    val market = MutableStateFlow("in")
    val signals = MutableStateFlow(Res<SignalsResponse>())
    val liveSignals = MutableStateFlow<Map<String, StockSignals>>(emptyMap())
    val usLive = MutableStateFlow<Map<String, LiveQuote>>(emptyMap())
    val usClosed = MutableStateFlow(true)
    private var signalsPoll: Job? = null

    fun setMarket(m: String) {
        if (m == market.value && signals.value.data != null) return
        market.value = m
        signals.value = Res()
        liveSignals.value = emptyMap()
        loadAll()
    }

    /** The Signals page: the holdings' signals and, for India, the Chartink Stage 2 list. */
    fun loadAll() {
        loadSignals()
        if (market.value == "in") loadStage2()
    }

    /** Opening the page: load whatever is missing (the Overview may already have loaded the holdings' signals, but not the Stage 2 list). */
    fun ensureLoaded() {
        if (signals.value.data == null && !signals.value.loading) loadSignals()
        if (market.value == "in" && stage2.value.data == null && !stage2.value.loading) loadStage2()
    }

    /** One refresh for the page: India re-reads Chartink and computes the list and the holdings together; the US computes the holdings. */
    fun refreshAll() {
        if (market.value == "us") refreshSignals() else refreshStage2()
    }

    fun loadSignals() {
        val m = market.value
        signalsPoll?.cancel()
        signalsPoll = viewModelScope.launch {
            signals.value = signals.value.copy(loading = true, problem = null)
            // keep reading while a refresh job runs, so its progress shows
            while (isActive) {
                try {
                    val res = api.signals(m)
                    signals.value = Res(data = res)
                    if (res.job.state != "running") break
                } catch (e: Exception) {
                    signals.value = Res(data = signals.value.data, problem = e.problem())
                    break
                }
                delay(2000)
            }
            if (m == "us") runCatching { api.usLive() }.getOrNull()?.let { usLive.value = it.quotes; usClosed.value = it.session_closed }
            // signals rebuilt on today's live price (empty when Kite is not logged in; the stored ones stay)
            runCatching { api.liveSignals(m) }.getOrNull()?.let { if (market.value == m) liveSignals.value = it.signals }
        }
    }

    fun refreshSignals() = viewModelScope.launch {
        try {
            api.refreshSignals(market.value)
        } catch (e: Exception) {
            signals.value = signals.value.copy(problem = e.problem())
            return@launch
        }
        loadSignals()
    }

    // --- Stage 2 -----------------------------------------------------------------------------------------

    val stage2 = MutableStateFlow(Res<Stage2Response>())
    val stage2Quotes = MutableStateFlow<Map<String, LiveQuote>>(emptyMap())
    val stage2Live = MutableStateFlow<Map<String, StockSignals>>(emptyMap())
    private var stage2Poll: Job? = null

    fun loadStage2() {
        stage2Poll?.cancel()
        stage2Poll = viewModelScope.launch {
            stage2.value = stage2.value.copy(loading = true, problem = null)
            while (isActive) {
                try {
                    val res = api.stage2()
                    stage2.value = Res(data = res)
                    if (res.job.state != "running") break
                } catch (e: Exception) {
                    stage2.value = Res(data = stage2.value.data, problem = e.problem())
                    break
                }
                delay(2000)
            }
            // the refresh job also computed the holdings, so read their signals again
            if (market.value == "in") {
                runCatching { api.signals("in") }.getOrNull()?.let { signals.value = Res(data = it) }
                runCatching { api.liveSignals("in") }.getOrNull()?.let { if (market.value == "in") liveSignals.value = it.signals }
            }
            runCatching { api.stage2Live() }.getOrNull()?.let { stage2Quotes.value = it.quotes }
            runCatching { api.stage2LiveSignals() }.getOrNull()?.let { stage2Live.value = it.signals }
        }
    }

    fun refreshStage2() = viewModelScope.launch {
        try {
            api.refreshStage2()
        } catch (e: Exception) {
            stage2.value = stage2.value.copy(problem = e.problem())
            return@launch
        }
        loadStage2()
    }

    // --- one stock: momentum and strategies ------------------------------------------------------------------

    val momentum = MutableStateFlow(Res<MomentumAnalysis>())
    val swing = MutableStateFlow(Res<StrategyResult>())
    val ath = MutableStateFlow(Res<StrategyResult>())

    fun analyse(symbol: String) = run(momentum, keep = false) { api.momentum(symbol.trim().uppercase()) }

    fun runStrategy(kind: String, symbol: String) =
        if (kind == "ath") run(ath, keep = false) { api.athStrategy(symbol.trim().uppercase()) }
        else run(swing, keep = false) { api.swingStrategy(symbol.trim().uppercase()) }

    // --- brokers ---------------------------------------------------------------------------------------------

    val catalog = MutableStateFlow(Res<List<BrokerCatalogItem>>())
    val brokerBusy = MutableStateFlow(false)
    val brokerMessage = MutableStateFlow<Problem?>(null)

    fun loadCatalog() = run(catalog) { api.brokerCatalog() }

    /** Adds a connection and hands back what to do next: a credentials form, a login link, or nothing. */
    fun addConnection(item: BrokerCatalogItem, label: String, then: (BrokerSession) -> Unit) = viewModelScope.launch {
        brokerBusy.value = true
        try {
            val created = api.addConnection(item.broker_name, label)
            loadCatalog()
            then(created)
        } catch (e: Exception) {
            brokerMessage.value = Problem("Could not add the connection: ${e.message}")
        } finally {
            brokerBusy.value = false
        }
    }

    fun saveCredentials(connectionId: String, fields: Map<String, String>, then: (CredentialSaveResponse) -> Unit) = viewModelScope.launch {
        brokerBusy.value = true
        try {
            then(api.saveCredentials(connectionId, fields))
        } catch (e: Exception) {
            brokerMessage.value = Problem("Could not save: ${e.message}")
        } finally {
            brokerBusy.value = false
        }
    }

    fun removeConnection(connectionId: String, then: () -> Unit) = viewModelScope.launch {
        brokerBusy.value = true
        try {
            api.deleteConnection(connectionId)
            loadCatalog()
            then()
        } catch (e: Exception) {
            brokerMessage.value = Problem("Could not remove the connection: ${e.message}")
        } finally {
            brokerBusy.value = false
        }
    }

    // --- overview panels ---------------------------------------------------------------------------------

    val history = MutableStateFlow(Res<List<HistoryPoint>>())
    val targets = MutableStateFlow(Res<Map<String, Double>>())
    val risk = MutableStateFlow(Res<RiskResponse>())

    fun loadOverviewPanels() {
        run(history) { api.history(365) }
        run(targets) { api.targets().targets }
        run(risk) { api.risk() }
    }

    fun saveTargets(values: Map<String, Double>) = run(targets) { api.saveTargets(values).targets }
}

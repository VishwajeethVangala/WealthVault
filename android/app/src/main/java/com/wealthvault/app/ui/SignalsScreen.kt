package com.wealthvault.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.wealthvault.app.data.Holding
import com.wealthvault.app.data.LiveQuote
import com.wealthvault.app.data.StockSignals

/** One stock, with every broker's lots of it added together (as the web app's holdings model does). */
data class Instrument(
    val key: String,
    val sym: String,
    val symbols: List<String>,
    val brokers: List<String>,
    val qty: Double,
    val inv: Double,
    val cur: Double,
    val dayPct: Double?,
) {
    val avg get() = if (qty > 0) inv / qty else 0.0
    val ltp get() = if (qty > 0) cur / qty else 0.0
    val pnl get() = cur - inv
    val pnlPct get() = if (inv > 0) (cur / inv - 1) * 100 else null
}

private val BROKER_LABELS = mapOf("zerodha" to "Zerodha", "indmoney" to "INDmoney", "groww" to "Groww", "angelone" to "Angel One", "upstox" to "Upstox", "dhan" to "Dhan")

/** "conn_zerodha_live" reads as "Zerodha", as on the web app. */
fun brokerLabel(connectionId: String): String {
    val key = connectionId.removePrefix("conn_").substringBefore('_').lowercase()
    return BROKER_LABELS[key] ?: key.replaceFirstChar(Char::uppercase)
}

/** The ticker part of "DELL (Dell Technologies Inc.)" or "NSE:ABB". */
fun tickerOf(symbol: String) = symbol.substringAfter(':').trim().split(Regex("\\s+")).first().uppercase()

fun buildInstruments(holdings: List<Holding>, us: Boolean): List<Instrument> =
    holdings.filter { it.asset_class == if (us) "US_STOCKS" else "EQUITY" }
        .groupBy { if (us) tickerOf(it.instrument_symbol) else it.instrument_symbol.trim().uppercase() }
        .map { (key, lots) ->
            Instrument(
                key = key,
                sym = if (us) key else displayName(lots.first()),
                symbols = lots.map { it.instrument_symbol }.distinct(),
                brokers = lots.map { brokerLabel(it.connection_id) }.distinct(),
                qty = lots.sumOf { it.quantity },
                inv = lots.sumOf { it.invested },
                cur = lots.sumOf { it.current_value },
                dayPct = lots.firstNotNullOfOrNull { it.day_change_percentage },
            )
        }

private data class SigRow(val inst: Instrument, val sig: StockSignals?, val ltp: Double, val live: LiveQuote?, val reading: Reading)

private enum class SigFilter(val label: String) { All("All"), Bull("All bullish"), Mixed("Mixed"), Bear("All bearish"), Trade("In a trade") }

/** Opens a broker login page (Kite's daily login) in the browser. */
@Composable
fun LoginLinkButton(url: String, label: String = "Log in to Kite") {
    val context = LocalContext.current
    OutlinedButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }, shape = RoundedCornerShape(10.dp)) {
        Text(label, color = Wv.c.accent)
    }
}

/** A failed load, with the login link when that is what is missing. */
@Composable
fun ProblemNote(p: Problem) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Note(p.text, bad = p.authUrl == null)
        p.authUrl?.let { LoginLinkButton(it) }
    }
}

/** A thin progress track for a running refresh. */
@Composable
fun ProgressTrack(done: Int, total: Int) {
    val f = if (total > 0) done.toFloat() / total else 0f
    Box(Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)).background(Wv.c.surface2)) {
        Box(Modifier.fillMaxWidth(f).fillMaxHeight().clip(RoundedCornerShape(3.dp)).background(Wv.c.accent))
    }
}

/** Small KPI tiles, two to a row. */
@Composable
fun KpiGrid(tiles: List<Triple<String, String, String?>>, tones: List<androidx.compose.ui.graphics.Color?> = emptyList()) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        tiles.chunked(2).forEachIndexed { r, pair ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                pair.forEachIndexed { c, (label, value, foot) ->
                    WvCard(Modifier.weight(1f), padding = 12) {
                        Text(label, style = Wv.small, color = Wv.c.text3)
                        Text(value, style = Wv.title.copy(fontFeatureSettings = "tnum"), color = tones.getOrNull(r * 2 + c) ?: Wv.c.text)
                        if (foot != null) Text(foot, style = Wv.small, color = Wv.c.text3)
                    }
                }
                if (pair.size == 1) Box(Modifier.weight(1f))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SignalsScreen(vm: AppViewModel, avm: AnalysisViewModel, onStock: (String) -> Unit) {
    val holdings by vm.holdings.collectAsState()
    val market by avm.market.collectAsState()
    val res by avm.signals.collectAsState()
    val live by avm.liveSignals.collectAsState()
    val usLive by avm.usLive.collectAsState()
    val usClosed by avm.usClosed.collectAsState()
    var view by rememberSaveable { mutableStateOf("table") }
    var filter by rememberSaveable { mutableStateOf(SigFilter.All) }
    var q by rememberSaveable { mutableStateOf("") }
    val calls = rememberCallsState(defaultWindow = OPEN_WINDOW)
    val us = market == "us"
    val fmt = remember(us) { PriceFmt(us) }

    LaunchedEffect(Unit) { if (avm.signals.value.data == null) avm.loadSignals() }

    val all = holdings.data.orEmpty()
    val counts = mapOf("in" to buildInstruments(all, false).size, "us" to buildInstruments(all, true).size)
    val data = res.data
    val rows = remember(all, data, live, usLive, us) {
        val map = data?.symbol_map.orEmpty()
        val sigs = data?.signals.orEmpty() + live
        // the same stock at two brokers (e.g. "IDEAFORGE" and INDmoney's "INDS26287 (...)") is one row when the signals know both as one exchange id
        buildInstruments(all, us).groupBy { inst -> inst.symbols.firstNotNullOfOrNull { map[it] } ?: inst.key }.values.map { group ->
            if (group.size == 1) group.first() else group.first().copy(
                symbols = group.flatMap { it.symbols }.distinct(),
                brokers = group.flatMap { it.brokers }.distinct(),
                qty = group.sumOf { it.qty }, inv = group.sumOf { it.inv }, cur = group.sumOf { it.cur },
                sym = group.map { it.sym }.minBy { it.length },
            )
        }.map { inst ->
            val id = inst.symbols.firstNotNullOfOrNull { map[it] }
            val sig = id?.let { sigs[it] }
            val lq = if (us) usLive[inst.key] else null
            val ltp = if (us) lq?.price ?: sig?.momentum?.last_price ?: 0.0 else inst.ltp
            SigRow(inst, sig, ltp, lq, readSignals(sig, ltp))
        }
    }
    val withM = rows.filter { it.sig?.momentum != null }
    val up = withM.count { momentumLean(it.sig!!.momentum!!) == Lean.Bull }
    val down = withM.count { momentumLean(it.sig!!.momentum!!) == Lean.Bear }
    val swingIn = rows.filter { it.sig?.swing?.state == "IN_POSITION" }
    val athIn = rows.filter { it.sig?.ath?.state == "IN_POSITION" }
    val review = rows.filter { it.reading.alignment == Agreement.AllBear }
    val covered = rows.count { hasAnySignal(it.sig) }
    val job = data?.job
    val running = job?.state == "running"
    val visible = rows.filter { r ->
        val needle = q.trim().lowercase()
        (needle.isEmpty() || "${r.inst.sym} ${r.sig?.name.orEmpty()}".lowercase().contains(needle)) && when (filter) {
            SigFilter.All -> true
            SigFilter.Bull -> r.reading.alignment == Agreement.AllBull
            SigFilter.Mixed -> r.reading.alignment == Agreement.Mixed
            SigFilter.Bear -> r.reading.alignment == Agreement.AllBear
            SigFilter.Trade -> r.sig?.swing?.state == "IN_POSITION" || r.sig?.ath?.state == "IN_POSITION"
        }
    }.sortedByDescending { it.inst.cur }
    val sources = rows.map { CallSource(code = it.inst.key, name = it.sig?.name ?: it.inst.sym, held = true, sig = it.sig, ltp = it.ltp) }

    PullToRefreshBox(isRefreshing = res.loading && !running, onRefresh = { avm.loadSignals() }) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { PageTitle("Equity signals", "Momentum, Swing V2.1 and the ATH breakout on each stock you hold") }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Seg(listOf("in" to "India  ${counts["in"]}", "us" to "US  ${counts["us"]}"), market) { avm.setMarket(it) }
                        Seg(listOf("table" to "Holdings", "calls" to "Calls"), view) { view = it }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        PrimaryButton(if (running) "Refreshing…" else "Refresh signals", busy = running) { avm.refreshSignals() }
                        if (us) Badge(if (usClosed) "US market closed" else "US market open", if (usClosed) Tone.Off else Tone.Ok)
                        else if (live.isNotEmpty()) Badge("On live prices", Tone.Ok)
                    }
                    if (running && job != null) {
                        ProgressTrack(job.done, job.total)
                        Text("${job.done} of ${job.total} stocks", style = Wv.small, color = Wv.c.text3)
                    }
                }
            }
            res.problem?.let { item { ProblemNote(it) } }
            if (job?.state == "error") item { ProblemNote(Problem("Refresh stopped. ${job.message.orEmpty()}", job.auth_url)) }
            if (holdings.loading && all.isEmpty()) item { Note("Loading your holdings…") }
            holdings.error?.let { e ->
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Note("Holdings did not load: $e", bad = true)
                        OutlinedButton(onClick = { vm.refreshAll() }, shape = RoundedCornerShape(10.dp)) { Text("Try again", color = Wv.c.text) }
                    }
                }
            }

            if (rows.isNotEmpty()) {
                item {
                    KpiGrid(
                        listOf(
                            Triple("Stocks covered", "$covered / ${rows.size}", if (rows.size - covered > 0) "${rows.size - covered} without signals" else "All analysed"),
                            Triple("Momentum", "$up / ${withM.size - up - down} / $down", "Uptrend / neutral / downtrend"),
                            Triple("In a Swing trade", "${swingIn.size}", "${compact(swingIn.sumOf { it.inst.cur })} of holdings"),
                            Triple("In an ATH trade", "${athIn.size}", "${compact(athIn.sumOf { it.inst.cur })} of holdings"),
                            Triple("Review: all bearish", "${review.size}", "${compact(review.sumOf { it.inst.cur })} of holdings"),
                        ),
                        listOf(null, null, null, null, if (review.isNotEmpty()) Wv.c.loss else null),
                    )
                }
            }

            when {
                rows.isEmpty() && !holdings.loading && holdings.error == null -> item {
                    Note(if (us) "No US stocks or ETFs in your portfolio." else "No stock holdings. Indian-listed stocks and ETFs show here; mutual funds, NPS and gold are not included.")
                }
                covered == 0 && !running && !res.loading && data != null -> item {
                    Note("Signals have not been computed yet. Press Refresh signals to analyse your ${rows.size} stocks. Results are saved, so the page opens instantly after that.")
                }
                view == "calls" -> callsView(sources, fmt, if (us) usSessionOpen() else indiaSessionOpen(), calls) { if (!us) onStock(it.sig?.instrument ?: it.code) }
                else -> {
                    item {
                        OutlinedTextField(q, { q = it }, placeholder = { Text("Search a stock") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    }
                    item {
                        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            SigFilter.entries.forEach { f -> Chip(f.label, filter == f) { filter = f } }
                        }
                    }
                    items(visible, key = { it.inst.key }) { r -> SignalCard(r, fmt, us) { if (!us) onStock(r.sig?.instrument?.ifBlank { null } ?: tickerOf(r.inst.symbols.first())) } }
                    if (visible.isEmpty()) item { Note("No stocks match this filter.") }
                }
            }
            item {
                Text(
                    "Swing V2.1 and ATH entries are the strategies' own signals on daily candles, not your actual buys. \"Since entry\" compares today's price with the strategy entry price, per share" +
                        (if (us) ", in US dollars; invested, current and P&L stay in rupees" else "") +
                        ". Bullish: uptrend, a strategy in position, or a buy signal. Bearish: downtrend, a failing Swing trend filter, a sell signal or an exit. This is a rules-based reading of past prices, not advice.",
                    style = Wv.small, color = Wv.c.text3,
                )
            }
        }
    }
}

@Composable
private fun SignalCard(r: SigRow, fmt: PriceFmt, us: Boolean, onOpen: () -> Unit) {
    val inst = r.inst
    WvCard(padding = 14, modifier = if (!us) Modifier.clickable(onClick = onOpen) else Modifier) {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Text(r.sig?.name?.takeIf { us } ?: inst.sym, style = Wv.title, color = Wv.c.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text("${inst.brokers.joinToString(" + ")} · ${trimQty(inst.qty)} @ ${price(inst.avg)}", style = Wv.small, color = Wv.c.text3)
                Row {
                    Text("LTP ${fmt.price(r.ltp)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text2)
                    val day = r.live?.day_change_pct ?: if (!us) inst.dayPct else null
                    day?.let { Text("  ${pct(it)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(it)) }
                }
                if (r.sig?.history_status == "partial") Text("Partial price history", style = Wv.small, color = Wv.c.warn)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(money(inst.cur), style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                Text(signedMoney(inst.pnl), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(inst.pnl))
                Text(pct(inst.pnlPct), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(inst.pnlPct))
            }
        }
        HorizontalDivider(color = Wv.c.border)
        SignalBlock(r.sig, r.ltp, r.reading, fmt)
    }
}

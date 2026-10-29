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
import androidx.compose.runtime.mutableIntStateOf
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
import com.wealthvault.app.data.AutoRefresh
import com.wealthvault.app.data.Holding
import com.wealthvault.app.data.LiveQuote
import com.wealthvault.app.data.SignalsResponse
import com.wealthvault.app.data.Stage2Response
import com.wealthvault.app.data.Stage2Row
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

/** Opens a broker login page (Kite's daily login) in the browser. */
@Composable
fun LoginLinkButton(url: String, label: String = "Log in to Kite") {
    val context = LocalContext.current
    OutlinedButton(onClick = { openLink(context, url) }, shape = RoundedCornerShape(10.dp)) {
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
            }
        }
    }
}

/** Where to land on the Signals tab when another screen links to it (the web passes these in the URL). */
data class SignalsPreset(
    val view: String = "calls",
    val side: String? = null,
    val window: Int? = null,
    val filter: String? = null,
    val source: String? = null,
    val market: String? = null,
)

/**
 * One row of the Signals page: a stock you hold, a stock on the Chartink Stage 2 list, or both (shown once).
 * [open] is what the Momentum page is opened with.
 */
private data class SigRow(
    val key: String,
    val code: String,
    val name: String,
    val inst: Instrument?,
    val s2: Stage2Row?,
    val sig: StockSignals?,
    val ltp: Double,
    val dayPct: Double?,
    val live: LiveQuote?,
    val fresh: Boolean,
    val reading: Reading,
    val open: String,
)

private enum class Source(val label: String) { All("Everything"), Held("My holdings"), Stage2("Stage 2"), New("New on Stage 2") }

private enum class SSort(val label: String) { Align("Agreement"), Day("Day change"), Momentum("Momentum"), Position("Your position"), Name("Name"), Cap("Market cap") }

private fun marketCap(v: Double?) = when {
    v == null || v <= 0 -> null
    v >= 1e5 -> String.format("₹%.2f L Cr", v / 1e5)
    else -> "₹" + price(v).removePrefix("₹").substringBefore('.') + " Cr"
}

private enum class SigFilter(val label: String) { All("All"), Bull("All bullish"), Mixed("Mixed"), Bear("All bearish"), Trade("In a trade"), Fresh("Fresh entries") }

private const val FRESH_DAYS = 10
private const val PAGE = 60

private fun titleCase(v: String) = v.split(' ').joinToString(" ") { w -> w.replaceFirstChar(Char::uppercase) }

/** Exchange id "NSE:INFY" -> "INFY"; also drops the trade-for-trade series suffix, so "MTARTECH-BE" matches "MTARTECH". */
private fun codeOf(id: String) = id.substringAfter(':').uppercase().replace(Regex("-(BE|BZ|BL|IL)$"), "")

private fun isFresh(sig: StockSignals?) =
    (sig?.ath?.state == "IN_POSITION" && (sig.ath.bars_held ?: 999) <= FRESH_DAYS)

/** Chartink + holdings - on both = total, counted once. */
private data class Breakdown(val chartink: Int, val held: Int, val both: Int) {
    val total get() = chartink + held - both
    fun text(us: Boolean) = if (us) "Holdings $held" else "Chartink $chartink + Holdings $held" + (if (both > 0) " − $both on both" else "") + " = $total"
}

private fun buildRows(
    holdings: List<Holding>,
    held: SignalsResponse?,
    heldLive: Map<String, StockSignals>,
    stage2: Stage2Response?,
    stage2Live: Map<String, StockSignals>,
    quotes: Map<String, LiveQuote>,
    usLive: Map<String, LiveQuote>,
    us: Boolean,
): List<SigRow> {
    val map = held?.symbol_map.orEmpty()
    val heldSigs = held?.signals.orEmpty() + heldLive
    // the same stock at two brokers (e.g. "IDEAFORGE" and INDmoney's "INDS26287 (...)") is one row when the signals know both as one exchange id
    val instruments = buildInstruments(holdings, us).groupBy { inst -> inst.symbols.firstNotNullOfOrNull { map[it] } ?: inst.key }.values.map { group ->
        if (group.size == 1) group.first() else group.first().copy(
            symbols = group.flatMap { it.symbols }.distinct(),
            brokers = group.flatMap { it.brokers }.distinct(),
            qty = group.sumOf { it.qty }, inv = group.sumOf { it.inv }, cur = group.sumOf { it.cur },
            sym = group.map { it.sym }.minBy { it.length },
        )
    }

    if (us) {
        return instruments.map { inst ->
            val id = inst.symbols.firstNotNullOfOrNull { map[it] }
            val sig = id?.let { heldSigs[it] }
            val lq = usLive[inst.key]
            val ltp = lq?.price ?: sig?.momentum?.last_price ?: 0.0
            SigRow("us:${inst.key}", inst.sym, sig?.name ?: inst.sym, inst, null, sig, ltp, lq?.day_change_pct ?: inst.dayPct, lq, false, readSignals(sig, ltp), inst.key)
        }
    }

    val out = mutableListOf<SigRow>()
    val byCode = mutableMapOf<String, Int>()
    stage2?.list?.rows.orEmpty().forEach { row ->
        val code = row.nsecode.uppercase()
        val sig = stage2Live[code] ?: stage2?.signals?.get(code)
        val lq = quotes[row.nsecode]
        val ltp = lq?.price ?: row.close
        byCode[code] = out.size
        out += SigRow("s2:$code", row.nsecode, row.name, null, row, sig, ltp, lq?.day_change_pct ?: row.per_chg, null, isFresh(sig), readSignals(sig, ltp), sig?.instrument?.ifBlank { null } ?: "NSE:${row.nsecode}")
    }
    instruments.forEach { inst ->
        val id = inst.symbols.firstNotNullOfOrNull { map[it] }
        val at = id?.let { byCode[codeOf(it)] }
        if (at != null) {
            // on both lists: keep the Chartink row, attach the position
            val m = out[at]
            val sig = m.sig ?: id?.let { heldSigs[it] }
            val ltp = quotes[m.code]?.price ?: inst.ltp
            out[at] = m.copy(inst = inst, sig = sig, ltp = ltp, fresh = isFresh(sig), reading = readSignals(sig, ltp))
        } else {
            val sig = id?.let { heldSigs[it] }
            out += SigRow("held:${inst.key}", inst.key, sig?.name ?: inst.sym, inst, null, sig, inst.ltp, inst.dayPct, null, isFresh(sig), readSignals(sig, inst.ltp), sig?.instrument?.ifBlank { null } ?: tickerOf(inst.symbols.first()))
        }
    }
    return out
}

/** "Auto refresh every 15 min in market hours, next 10:30", plus why the last run today did not run, if it did not. */
private fun autoLine(auto: AutoRefresh?): String? {
    if (auto == null || !auto.enabled) return null
    val ist = java.time.ZoneId.of("Asia/Kolkata")
    val today = java.time.LocalDate.now(ist)
    val parse = { iso: String -> runCatching { java.time.OffsetDateTime.parse(iso).atZoneSameInstant(ist) }.getOrNull() }
    val hm = java.time.format.DateTimeFormatter.ofPattern("HH:mm")
    val next = auto.next_run?.let(parse)?.let { if (it.toLocalDate() == today) it.format(hm) else it.format(java.time.format.DateTimeFormatter.ofPattern("EEE HH:mm")) }
    val last = auto.last_run?.takeIf { it.outcome != "ran" }?.let { r ->
        parse(r.slot)?.takeIf { it.toLocalDate() == today }?.let { " (the ${it.format(hm)} run ${if (r.outcome == "skipped") "was skipped" else "failed"}: ${r.message})" }
    }.orEmpty()
    return "Auto refresh every ${auto.every_minutes} min in market hours" + (next?.let { ", next $it" } ?: "") + last
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
    val s2Res by avm.stage2.collectAsState()
    val quotes by avm.stage2Quotes.collectAsState()
    val s2Live by avm.stage2Live.collectAsState()
    var view by rememberSaveable { mutableStateOf("calls") }
    var source by rememberSaveable { mutableStateOf(Source.All) }
    var filter by rememberSaveable { mutableStateOf(SigFilter.All) }
    var sector by rememberSaveable { mutableStateOf("all") }
    var q by rememberSaveable { mutableStateOf("") }
    var sort by rememberSaveable { mutableStateOf(SSort.Align) }
    var shown by remember { mutableIntStateOf(PAGE) }
    val calls = rememberCallsState(defaultWindow = OPEN_WINDOW)
    val us = market == "us"
    val fmt = remember(us) { PriceFmt(us) }
    val context = LocalContext.current

    LaunchedEffect(Unit) { avm.ensureLoaded() }
    val preset by avm.signalsPreset.collectAsState()
    LaunchedEffect(preset) {
        val p = preset ?: return@LaunchedEffect
        p.market?.let { if (it != avm.market.value) avm.setMarket(it) }
        view = p.view
        source = when (p.source) { "held" -> Source.Held; "stage2" -> Source.Stage2; "new" -> Source.New; else -> Source.All }
        filter = when (p.filter) { "all-bear" -> SigFilter.Bear; "all-bull" -> SigFilter.Bull; "mixed" -> SigFilter.Mixed; "trade" -> SigFilter.Trade; else -> SigFilter.All }
        p.side?.let { side ->
            calls.side = side
            calls.window = p.window ?: OPEN_WINDOW
            // a link to calls opens their sections, as the web does
            listOf("$side-${Kind.Ath}-${calls.window}").forEach { calls.open[it] = true }
        }
        shown = PAGE
        avm.signalsPreset.value = null
    }

    val all = holdings.data.orEmpty()
    val data = res.data
    val s2Data = if (us) null else s2Res.data
    val list = s2Data?.list
    val rows = remember(all, data, live, s2Data, s2Live, quotes, usLive, us) { buildRows(all, data, live, s2Data, s2Live, quotes, usLive, us) }
    val scoped = rows.filter { r ->
        when (source) {
            Source.All -> true
            Source.Held -> r.inst != null
            Source.Stage2 -> r.s2 != null
            Source.New -> r.s2?.is_new == true
        }
    }
    val sourceCounts = mapOf(Source.All to rows.size, Source.Held to rows.count { it.inst != null }, Source.Stage2 to rows.count { it.s2 != null }, Source.New to rows.count { it.s2?.is_new == true })

    // India's job covers the Chartink list and the holdings; the US job is the holdings job
    val job = if (us) data?.job else s2Data?.job
    val running = job?.state == "running"
    val breakdown = if (!us && running && (job?.total ?: 0) > 0) Breakdown(job!!.list_count, job.holdings_count, job.overlap)
    else Breakdown(rows.count { it.s2 != null }, rows.count { it.inst != null }, rows.count { it.s2 != null && it.inst != null })

    val withM = scoped.filter { it.sig?.momentum != null }
    val up = withM.count { momentumLean(it.sig!!.momentum!!) == Lean.Bull }
    val down = withM.count { momentumLean(it.sig!!.momentum!!) == Lean.Bear }
    val covered = scoped.count { hasAnySignal(it.sig) }
    val bull = scoped.filter { it.reading.alignment == Agreement.AllBull }
    val reviewHeld = scoped.count { it.inst != null && it.reading.alignment == Agreement.AllBear }
    val needle = q.trim().lowercase()
    val sectors = scoped.mapNotNull { it.s2?.sector?.takeIf(String::isNotBlank) }.groupingBy { it }.eachCount().entries.sortedByDescending { it.value }
    val visible = scoped.filter { r ->
        (needle.isEmpty() || "${r.name} ${r.code}".lowercase().contains(needle)) &&
            (sector == "all" || r.s2?.sector == sector) &&
            when (filter) {
                SigFilter.All -> true
                SigFilter.Bull -> r.reading.alignment == Agreement.AllBull
                SigFilter.Mixed -> r.reading.alignment == Agreement.Mixed
                SigFilter.Bear -> r.reading.alignment == Agreement.AllBear
                SigFilter.Trade -> r.sig?.ath?.state == "IN_POSITION"
                SigFilter.Fresh -> r.fresh
            }
    }.let { l ->
        when (sort) {
            SSort.Align -> l.sortedWith(compareByDescending<SigRow> { if (it.sig != null) it.reading.alignment.order else -1 }.thenByDescending { it.inst?.cur ?: 0.0 }.thenByDescending { it.dayPct ?: -999.0 })
            SSort.Day -> l.sortedByDescending { it.dayPct ?: -999.0 }
            SSort.Momentum -> l.sortedByDescending { it.sig?.momentum?.let { m -> m.score.toDouble() / (m.max.takeIf { x -> x > 0 } ?: 1) } ?: -1.0 }
            SSort.Position -> l.sortedByDescending { it.inst?.cur ?: -1.0 }
            SSort.Name -> l.sortedBy { it.name.lowercase() }
            SSort.Cap -> l.sortedByDescending { it.s2?.market_cap ?: -1.0 }
        }
    }
    val sources = scoped.map {
        CallSource(code = it.s2?.nsecode ?: it.code, name = it.name, sector = it.s2?.sector?.let(::titleCase), held = it.inst != null, isNew = it.s2?.is_new == true, sig = it.sig, ltp = it.ltp)
    }
    val byOpen = scoped.associateBy { it.s2?.nsecode ?: it.code }

    PullToRefreshBox(isRefreshing = (res.loading || s2Res.loading) && !running, onRefresh = { avm.loadAll() }) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { PageTitle("Signals", "Momentum and the ATH breakout on the stocks you hold and your Chartink Stage 2 list") }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    // one control bar: which stocks, then the refresh; a quiet status line under it
                    Seg(listOf("in" to "India", "us" to "US"), market) { avm.setMarket(it); shown = PAGE }
                    if (!us && list != null) {
                        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Source.entries.forEach { src -> Chip("${src.label} ${sourceCounts[src]}", source == src) { source = src; shown = PAGE } }
                        }
                    }
                    PrimaryButton(
                        when {
                            running && job?.trigger == "schedule" -> "Auto refresh running…"
                            running -> "Refreshing…"
                            us -> "Refresh signals"
                            else -> "Refresh Momentum Stocks"
                        },
                        busy = running, modifier = Modifier.fillMaxWidth(),
                    ) { avm.refreshAll() }
                    if (running && job != null) {
                        ProgressTrack(job.done, job.total)
                        Text("${job.done} of ${job.total} stocks", style = Wv.small, color = Wv.c.text3)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (us) Badge(if (usClosed) "US market closed" else "US market open", if (usClosed) Tone.Off else Tone.Ok)
                        else if (live.isNotEmpty() || s2Live.isNotEmpty()) Badge("On live prices", Tone.Ok)
                        else Badge("Stored prices", Tone.Off)
                    }
                    Text(
                        listOfNotNull(
                            breakdown.text(us),
                            list?.takeIf { !us }?.let { "list read ${longDate(it.date)}" },
                            if (us) null else autoLine(s2Data?.auto),
                        ).joinToString(" · "),
                        style = Wv.small, color = Wv.c.text3,
                    )
                }
            }
            res.problem?.let { item { ProblemNote(it) } }
            s2Res.problem?.takeIf { !us }?.let { item { ProblemNote(it) } }
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
                            Triple(if (us) "US stocks you hold" else "Stocks in view", "${scoped.size}",
                                if (us) (if (scoped.size - covered > 0) "${scoped.size - covered} without signals" else "All analysed")
                                else "${scoped.count { it.inst != null }} held · ${scoped.count { it.s2 != null }} on Stage 2 · ${scoped.count { it.inst != null && it.s2 != null }} both"),
                            Triple("Momentum", "$up / ${withM.size - up - down} / $down", "Uptrend / neutral / downtrend"),
                            Triple("In an ATH trade", "${scoped.count { it.sig?.ath?.state == "IN_POSITION" }}", "${scoped.count { it.fresh }} opened in the last $FRESH_DAYS days"),
                            Triple("Both bullish", "${bull.size}", "${bull.count { it.inst != null }} held" + if (reviewHeld > 0) " · $reviewHeld held all bearish" else ""),
                        ),
                        listOf(null, null, null, null, if (bull.isNotEmpty()) Wv.c.gain else null),
                    )
                }
                item { Seg(listOf("calls" to "Buy & sell calls", "table" to "All stocks  ${scoped.size}"), view, Modifier.fillMaxWidth()) { view = it } }
            }

            when {
                rows.isEmpty() && !holdings.loading && holdings.error == null && !res.loading && !s2Res.loading -> item {
                    Note(if (us) "No US stocks or ETFs in your portfolio." else "Nothing to analyse yet. Press Refresh Momentum Stocks: it reads your Chartink Stage 2 screener, then runs it and every Indian stock you hold through the three signals.")
                }
                covered == 0 && !running && !res.loading && !s2Res.loading && data != null && rows.isNotEmpty() -> item {
                    Note("Signals have not been computed yet. Press ${if (us) "Refresh signals" else "Refresh Momentum Stocks"} to analyse ${rows.size} stocks. Results are saved, so the page opens instantly after that.")
                }
                view == "calls" -> callsView(sources, fmt, if (us) usSessionOpen() else indiaSessionOpen(), calls) { c ->
                    if (!us) onStock(byOpen[c.code]?.open ?: c.sig?.instrument ?: "NSE:${c.code}")
                }
                else -> {
                    item { OutlinedTextField(q, { q = it; shown = PAGE }, placeholder = { Text("Search a stock") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                    // filter, sort and sector chips as one group with room between the rows, so taps land where aimed
                    item {
                        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                SigFilter.entries.forEach { f -> Chip(f.label, filter == f) { filter = f; shown = PAGE } }
                            }
                            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text("Sort", style = Wv.small, color = Wv.c.text3)
                                SSort.entries.filter { it != SSort.Cap || (!us && list != null) }.filter { it != SSort.Position || scoped.any { r -> r.inst != null } }.forEach { k ->
                                    Chip(k.label, sort == k) { sort = k; shown = PAGE }
                                }
                            }
                            if (sectors.isNotEmpty()) {
                                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Chip("All sectors", sector == "all") { sector = "all"; shown = PAGE }
                                    sectors.forEach { (name, n) -> Chip("${titleCase(name)} $n", sector == name) { sector = name; shown = PAGE } }
                                }
                            }
                        }
                    }
                    items(visible.take(shown), key = { it.key }) { r -> SignalCard(r, fmt, us) { if (!us) onStock(r.open) } }
                    if (visible.isEmpty()) item { Note("No stocks match this filter.") }
                    if (visible.size > shown) {
                        item {
                            OutlinedButton(onClick = { shown += PAGE }, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                                Text("Show ${minOf(PAGE, visible.size - shown)} more of ${visible.size - shown}", color = Wv.c.text)
                            }
                        }
                    }
                }
            }

            if (!us && list != null) {
                if (view == "table" && list.dropped.isNotEmpty() && source != Source.Held) {
                    item {
                        WvCard {
                            Label("Dropped out of Stage 2 since ${list.previous_date ?: "the last read"}")
                            Text(list.dropped.joinToString(", ") { it.name.ifBlank { it.nsecode } }, style = Wv.sub, color = Wv.c.text2)
                        }
                    }
                }
                item {
                    WvCard {
                        Label("Stage 2 screener")
                        Text(
                            "Stage 2 stocks come from your saved Chartink screener, read ${longDate(list.date)}. Edit it on Chartink and press Refresh; the app reads its current definition each time.",
                            style = Wv.sub, color = Wv.c.text2,
                        )
                        list.url?.let { url ->
                            OutlinedButton(onClick = { openLink(context, url) }, shape = RoundedCornerShape(10.dp)) {
                                Text("Open Chartink", color = Wv.c.text)
                            }
                        }
                    }
                }
            }
            item {
                Text(
                    "ATH entries are the strategy's own signals on daily candles, not your actual buys. \"Since entry\" compares the live price with the strategy entry price, per share" +
                        (if (us) ", in US dollars; position values stay in rupees" else "") +
                        ". Signals use today's live price as the latest bar, so they can change until the close; the \"last sessions\" windows are the finished sessions plus today. " +
                        "Bullish: uptrend, a strategy in position, or a buy signal. Bearish: downtrend, a sell signal or an exit. This is a rules-based reading of past prices, not advice.",
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
                Text(r.name, style = Wv.title, color = Wv.c.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    if (inst != null) Badge("Held", Tone.Ok)
                    if (r.s2 != null) Badge("Stage 2", Tone.Off)
                    if (r.s2?.is_new == true) Badge("New", Tone.Info)
                }
                Text(
                    listOfNotNull(r.code, r.s2?.sector?.takeIf(String::isNotBlank)?.let(::titleCase), marketCap(r.s2?.market_cap)).joinToString(" · "),
                    style = Wv.small, color = Wv.c.text3, maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
                // US stocks trade before and after the session too
                r.live?.ext_price?.takeIf { us && it != r.live.price }?.let { Text("extended ${fmt.price(it)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3) }
                if (inst != null) Text("${inst.brokers.joinToString(" + ")} · ${trimQty(inst.qty)} @ ${ownPrice(inst.avg)}", style = Wv.small, color = Wv.c.text3)
                if (r.sig?.history_status == "partial") Text("Partial price history", style = Wv.small, color = Wv.c.warn)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(fmt.price(r.ltp), style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                Text(pct(r.dayPct), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(r.dayPct))
            }
        }
        if (inst != null) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Your position", style = Wv.small, color = Wv.c.text3, modifier = Modifier.weight(1f))
                Text(money(inst.cur), style = Wv.small.copy(fontFeatureSettings = "tnum", fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                Text("  ${signedMoney(inst.pnl)} · ${pct(inst.pnlPct)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(inst.pnl))
            }
        }
        HorizontalDivider(color = Wv.c.border)
        SignalBlock(r.sig, r.ltp, r.reading, fmt)
    }
}

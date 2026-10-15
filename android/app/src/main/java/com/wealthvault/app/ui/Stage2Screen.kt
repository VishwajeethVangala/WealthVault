package com.wealthvault.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.wealthvault.app.data.Stage2Row
import com.wealthvault.app.data.StockSignals

private const val FRESH_DAYS = 10
private const val PAGE = 60

private data class S2Row(val row: Stage2Row, val sig: StockSignals?, val ltp: Double, val dayPct: Double?, val fresh: Boolean, val reading: Reading)

private enum class S2Filter(val label: String) { All("All"), New("New today"), Bull("All bullish"), Fresh("Fresh trades"), Held("You hold") }

private enum class S2Sort(val label: String) { Align("Agreement"), Day("Day change"), Momentum("Momentum"), Name("Name"), Cap("Market cap") }

private fun titleCase(v: String) = v.split(' ').joinToString(" ") { w -> w.replaceFirstChar(Char::uppercase) }

/** Chartink reports market cap in crore rupees. */
private fun marketCap(v: Double?) = when {
    v == null || v <= 0 -> "—"
    v >= 1e5 -> String.format("₹%.2f L Cr", v / 1e5)
    else -> "₹" + money(v).removePrefix("₹") + " Cr"
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Stage2Screen(avm: AnalysisViewModel, onStock: (String) -> Unit) {
    val res by avm.stage2.collectAsState()
    val quotes by avm.stage2Quotes.collectAsState()
    val live by avm.stage2Live.collectAsState()
    var view by rememberSaveable { mutableStateOf("calls") }
    var filter by rememberSaveable { mutableStateOf(S2Filter.All) }
    var sort by rememberSaveable { mutableStateOf(S2Sort.Align) }
    var sector by rememberSaveable { mutableStateOf("all") }
    var q by rememberSaveable { mutableStateOf("") }
    var shown by remember { mutableIntStateOf(PAGE) }
    val calls = rememberCallsState(defaultWindow = 2)
    val fmt = remember { PriceFmt(false) }
    val context = LocalContext.current

    LaunchedEffect(Unit) { if (avm.stage2.value.data == null) avm.loadStage2() }

    val data = res.data
    val list = data?.list
    val rows = remember(data, quotes, live) {
        list?.rows.orEmpty().map { row ->
            val code = row.nsecode.uppercase()
            val sig = live[code] ?: data?.signals?.get(code)
            val lq = quotes[row.nsecode]
            val ltp = lq?.price ?: row.close
            val fresh = (sig?.swing?.state == "IN_POSITION" && (sig.swing.bars_held ?: 999) <= FRESH_DAYS) ||
                (sig?.ath?.state == "IN_POSITION" && (sig.ath.bars_held ?: 999) <= FRESH_DAYS)
            S2Row(row, sig, ltp, lq?.day_change_pct ?: row.per_chg, fresh, readSignals(sig, ltp))
        }
    }
    val counts = mapOf(
        S2Filter.All to rows.size,
        S2Filter.New to rows.count { it.row.is_new == true },
        S2Filter.Bull to rows.count { it.reading.alignment == Agreement.AllBull },
        S2Filter.Fresh to rows.count { it.fresh },
        S2Filter.Held to rows.count { it.row.held },
    )
    val sectors = rows.mapNotNull { it.row.sector?.takeIf(String::isNotBlank) }.groupingBy { it }.eachCount().entries.sortedByDescending { it.value }
    val needle = q.trim().lowercase()
    val visible = rows.filter { r ->
        (needle.isEmpty() || "${r.row.name} ${r.row.nsecode}".lowercase().contains(needle)) &&
            (sector == "all" || r.row.sector == sector) &&
            when (filter) {
                S2Filter.All -> true
                S2Filter.New -> r.row.is_new == true
                S2Filter.Bull -> r.reading.alignment == Agreement.AllBull
                S2Filter.Fresh -> r.fresh
                S2Filter.Held -> r.row.held
            }
    }.let { l ->
        when (sort) {
            S2Sort.Align -> l.sortedWith(compareByDescending<S2Row> { if (it.sig != null) it.reading.alignment.order else -1 }.thenByDescending { it.dayPct ?: -999.0 })
            S2Sort.Day -> l.sortedByDescending { it.dayPct ?: -999.0 }
            S2Sort.Momentum -> l.sortedByDescending { it.sig?.momentum?.let { m -> m.score.toDouble() / (m.max.takeIf { x -> x > 0 } ?: 1) } ?: -1.0 }
            S2Sort.Name -> l.sortedBy { it.row.name.lowercase() }
            S2Sort.Cap -> l.sortedByDescending { it.row.market_cap ?: -1.0 }
        }
    }
    val withM = rows.filter { it.sig?.momentum != null }
    val up = withM.count { momentumLean(it.sig!!.momentum!!) == Lean.Bull }
    val down = withM.count { momentumLean(it.sig!!.momentum!!) == Lean.Bear }
    val job = data?.job
    val running = job?.state == "running"
    val sources = rows.map {
        CallSource(code = it.row.nsecode, name = it.row.name, sector = it.row.sector?.let(::titleCase), held = it.row.held, isNew = it.row.is_new == true, sig = it.sig, ltp = it.ltp)
    }

    PullToRefreshBox(isRefreshing = res.loading && !running, onRefresh = { avm.loadStage2() }) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                PageTitle(
                    "Stage 2",
                    if (list != null) "${list.rows.size} stocks in a Stage 2 uptrend · Chartink list of ${longDate(list.date)}" else "Stocks in a Stage 2 uptrend, from your Chartink screener",
                )
            }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Seg(listOf("calls" to "Buy & sell calls", "list" to "List"), view) { view = it }
                        if (live.isNotEmpty()) Badge("On live prices", Tone.Ok)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        PrimaryButton(if (running) "Refreshing…" else "Refresh list", busy = running) { avm.refreshStage2() }
                        list?.url?.let { url ->
                            OutlinedButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }, shape = RoundedCornerShape(10.dp)) {
                                Text("Open Chartink", color = Wv.c.text)
                            }
                        }
                    }
                    if (running && job != null) {
                        ProgressTrack(job.done, job.total)
                        Text("${job.done} of ${job.total} stocks", style = Wv.small, color = Wv.c.text3)
                    }
                }
            }
            res.problem?.let { item { ProblemNote(it) } }
            if (job?.state == "error") item { ProblemNote(Problem("Refresh stopped. ${job.message.orEmpty()}", job.auth_url)) }
            if (data != null && list == null && !running) item { Note("The Stage 2 list has not been read yet. Press Refresh list.") }

            if (rows.isNotEmpty()) {
                item {
                    KpiGrid(
                        listOf(
                            Triple("On the list", "${rows.size}", "${counts[S2Filter.New]} new · ${list?.dropped?.size ?: 0} left today"),
                            Triple("Momentum", "$up / ${withM.size - up - down} / $down", "Uptrend / neutral / downtrend"),
                            Triple("In a Swing trade", "${rows.count { it.sig?.swing?.state == "IN_POSITION" }}", "Swing V2.1 positions"),
                            Triple("In an ATH trade", "${rows.count { it.sig?.ath?.state == "IN_POSITION" }}", "200-DMA ATH breakout"),
                        ),
                    )
                }
                if (view == "calls") {
                    callsView(sources, fmt, indiaSessionOpen(), calls) { onStock(it.sig?.instrument ?: "NSE:${it.code}") }
                } else {
                    item { OutlinedTextField(q, { q = it; shown = PAGE }, placeholder = { Text("Search a stock") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                    item {
                        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            S2Filter.entries.forEach { f -> Chip("${f.label} ${counts[f]}", filter == f) { filter = f; shown = PAGE } }
                        }
                    }
                    if (sectors.isNotEmpty()) {
                        item {
                            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Chip("All sectors", sector == "all") { sector = "all"; shown = PAGE }
                                sectors.forEach { (name, n) -> Chip("${titleCase(name)} $n", sector == name) { sector = name; shown = PAGE } }
                            }
                        }
                    }
                    item {
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Sort", style = Wv.small, color = Wv.c.text3)
                            S2Sort.entries.forEach { s -> Chip(s.label, sort == s) { sort = s } }
                        }
                    }
                    items(visible.take(shown), key = { it.row.nsecode }) { r -> Stage2Card(r, fmt) { onStock(r.sig?.instrument ?: "NSE:${r.row.nsecode}") } }
                    if (visible.isEmpty()) item { Note("No stocks match this filter.") }
                    if (visible.size > shown) {
                        item {
                            OutlinedButton(onClick = { shown += PAGE }, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                                Text("Show ${minOf(PAGE, visible.size - shown)} more of ${visible.size - shown}", color = Wv.c.text)
                            }
                        }
                    }
                    if (!list?.dropped.isNullOrEmpty() && filter == S2Filter.All && sector == "all" && needle.isEmpty()) {
                        item {
                            WvCard {
                                Label("Left the list today")
                                Text(list!!.dropped.joinToString(", ") { it.name.ifBlank { it.nsecode } }, style = Wv.sub, color = Wv.c.text2)
                            }
                        }
                    }
                }
            }
            item { Text("Stage 2 stocks come from your saved Chartink screener; signals are the same rules as on Equity signals. A rules-based reading of past prices, not advice.", style = Wv.small, color = Wv.c.text3) }
        }
    }
}

@Composable
private fun Stage2Card(r: S2Row, fmt: PriceFmt, onOpen: () -> Unit) {
    WvCard(padding = 14, modifier = Modifier.clickable(onClick = onOpen)) {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(r.row.name, style = Wv.title, color = Wv.c.text, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    if (r.row.is_new == true) Badge("New", Tone.Info)
                    if (r.row.held) Badge("Held", Tone.Ok)
                }
                Text(
                    listOfNotNull(r.row.nsecode, r.row.sector?.let(::titleCase), marketCap(r.row.market_cap).takeIf { it != "—" }).joinToString(" · "),
                    style = Wv.small, color = Wv.c.text3, maxLines = 2, overflow = TextOverflow.Ellipsis,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(fmt.price(r.ltp), style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                Text(pct(r.dayPct), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(r.dayPct))
            }
        }
        HorizontalDivider(color = Wv.c.border)
        SignalBlock(r.sig, r.ltp, r.reading, fmt)
    }
}

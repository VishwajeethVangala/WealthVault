package com.wealthvault.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.wealthvault.app.data.ASSET_CLASS_LABEL
import com.wealthvault.app.data.BrokerSession
import com.wealthvault.app.data.Holding
import com.wealthvault.app.data.HistoryPoint
import com.wealthvault.app.data.RiskResponse
import com.wealthvault.app.data.SignalsResponse
import com.wealthvault.app.data.StockSignals
import kotlinx.coroutines.delay
import kotlin.math.abs

/**
 * The Overview, as on the web (web/src/pages/ExecutiveOverview.tsx): net worth with a period chart, today against
 * the Nifty, a brief in words, a card per asset class, why today moved, signals on your holdings, allocation
 * against targets, risk and concentration, notes, the largest positions and the split by broker. Everything is
 * computed from the live holdings, so the broker and asset-class filters apply to all of it.
 */

private fun classLabel(cls: String) = ASSET_CLASS_LABEL[cls] ?: cls

@Composable
private fun classColor(cls: String) = Wv.c.classColors[cls] ?: Wv.c.text3

/** The Overview's reading of the signals on your holdings (web: components/dashboard/SignalsPanel.tsx). */
data class DashSignals(
    val sells: List<CallRow>,
    val buys: List<CallRow>,
    val review: List<CallSource>,
    val covered: Int,
    val hasExit: Boolean,
    val sellsPreset: SignalsPreset,
    val buysPreset: SignalsPreset,
    val reviewPreset: SignalsPreset,
    /** US tickers: their Momentum page is not available (it reads Kite's Indian prices) */
    val usCodes: Set<String>,
)

fun dashSignals(
    positions: List<Position>,
    inData: SignalsResponse?,
    usData: SignalsResponse?,
    liveIn: Map<String, StockSignals>,
    liveUs: Map<String, StockSignals>,
): DashSignals {
    fun make(cls: String, data: SignalsResponse?, live: Map<String, StockSignals>): List<CallSource> {
        if (data == null) return emptyList()
        val sigs = data.signals + live
        return positions.filter { it.cls == cls }.map { p ->
            val id = data.symbol_map[p.lots.first().holding.instrument_symbol]
            val sig = id?.let { sigs[it] }
            CallSource(
                code = if (cls == "US_STOCKS") tickerOf(p.sym) else p.sym,
                name = p.sym, held = true, sig = sig,
                ltp = if (cls == "US_STOCKS") sig?.momentum?.last_price ?: 0.0 else p.ltp,
            )
        }
    }
    val inSrc = make("EQUITY", inData, liveIn)
    val usSrc = make("US_STOCKS", usData, liveUs)
    val all = inSrc + usSrc
    val s7 = latestSessions(all, 7)
    val s2 = latestSessions(all, 2)
    val inFmt = PriceFmt(false)
    val usFmt = PriceFmt(true)
    val sells = (buildSells(inSrc, s7, inFmt, false) + buildSells(usSrc, s7, usFmt, false)).sortedByDescending { it.date }
    val buys = (buildBuys(inSrc, s2, 2, inFmt, false) + buildBuys(usSrc, s2, 2, usFmt, false)).filter { !it.waiting }.sortedByDescending { it.date }
    val review = all.filter { readSignals(it.sig, it.ltp).alignment == Agreement.AllBear }
    val usOnly = { rows: List<CallSource> -> rows.isNotEmpty() && rows.all { it in usSrc } }
    val market = { rows: List<CallRow> -> if (usOnly(rows.map { it.src })) "us" else "in" }
    return DashSignals(
        sells, buys, review,
        covered = all.count { hasAnySignal(it.sig) },
        hasExit = all.any { it.sig?.swing?.exits != null || it.sig?.ath?.exits != null },
        sellsPreset = SignalsPreset(view = "calls", side = "sell", market = market(sells), source = "held"),
        buysPreset = SignalsPreset(view = "calls", side = "buy", window = 2, market = market(buys), source = "held"),
        reviewPreset = SignalsPreset(view = "table", filter = "all-bear", market = if (usOnly(review)) "us" else "in", source = "held"),
        usCodes = usSrc.map { it.code }.toSet(),
    )
}

private data class Note2(val id: String, val tone: String, val title: String, val body: String)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OverviewScreen(
    vm: AppViewModel,
    avm: AnalysisViewModel,
    onSignals: (SignalsPreset) -> Unit,
    onHoldings: () -> Unit,
    onBrokers: () -> Unit,
    onStock: (String) -> Unit,
) {
    val summary by vm.summary.collectAsState()
    val holdingsRes by vm.holdings.collectAsState()
    val brokersRes by vm.brokers.collectAsState()
    val history by avm.history.collectAsState()
    val targets by avm.targets.collectAsState()
    val risk by avm.risk.collectAsState()
    val nifty by avm.nifty.collectAsState()
    val brokerFilter by vm.brokerFilter.collectAsState()
    val classFilter by vm.classFilter.collectAsState()
    val syncing by vm.syncing.collectAsState()
    val message by vm.message.collectAsState()
    val dashIn by avm.dashIn.collectAsState()
    val dashUs by avm.dashUs.collectAsState()
    val liveIn by avm.dashLiveIn.collectAsState()
    val liveUs by avm.dashLiveUs.collectAsState()
    val usQuotes by avm.dashUsQuotes.collectAsState()
    val dashFailed by avm.dashFailed.collectAsState()
    var period by rememberSaveable { mutableStateOf(Period.D1) }
    var editTargets by remember { mutableStateOf(false) }
    val context = LocalContext.current

    LaunchedEffect(Unit) { if (avm.history.value.data == null) avm.loadOverviewPanels() }
    // the Nifty moves through the session: read it again every minute while the market is open
    LaunchedEffect(Unit) {
        while (true) {
            delay(if (indiaSessionOpen()) 60_000 else 600_000)
            avm.loadNifty()
        }
    }

    val all = holdingsRes.data.orEmpty()
    val sessions = brokersRes.data.orEmpty()
    val filtered = remember(all, brokerFilter, classFilter) { applyFilters(all, brokerFilter, classFilter) }
    val positions = remember(filtered) { buildPositions(filtered) }
    val totals = remember(positions) { totalsOf(positions) }
    val hist = history.data.orEmpty()
    val fromDate = remember(hist, period) { baseline(hist, if (period == Period.D1) Period.M1 else period)?.date }
    val cards = remember(positions, hist, fromDate, totals) { classCards(positions, hist, fromDate, totals.cur) }
    val conc = remember(positions, totals) { concentration(positions, totals.cur) }
    val drawdown = remember(hist) { drawdownOf(hist) }
    val drift = remember(cards, targets.data, totals) { driftRows(cards, targets.data.orEmpty(), totals.cur) }
    val usdPct = cards.firstOrNull { it.cls == "US_STOCKS" }?.weight ?: 0.0
    // US stocks' average move in dollars today, weighted by value
    val usdMove = remember(all, usQuotes) {
        var num = 0.0
        var den = 0.0
        all.filter { it.asset_class == "US_STOCKS" }.forEach { h ->
            usQuotes[tickerOf(h.instrument_symbol)]?.day_change_pct?.let { p -> num += h.current_value * p; den += h.current_value }
        }
        if (den > 0) num / den else null
    }
    val dash = remember(positions, dashIn, dashUs, liveIn, liveUs) { dashSignals(positions, dashIn, dashUs, liveIn, liveUs) }
    val filterActive = brokerFilter.isNotEmpty() || classFilter.isNotEmpty()
    val notes = overviewNotes(sessions, positions, totals, drift, filtered, targets.data.orEmpty())
    val brief = overviewBrief(totals, cards, nifty, dash, drift, conc)
    val kite = sessions.firstOrNull { it.broker_name.contains("zerodha", ignoreCase = true) && !it.auth_url.isNullOrBlank() && needsLogin(it) }

    PullToRefreshBox(isRefreshing = holdingsRes.loading && all.isNotEmpty(), onRefresh = { vm.refreshAll(); avm.loadOverviewPanels() }) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f)) { PageTitle("Overview", summary.data?.snapshot?.as_of_date?.let { "As of ${longDate(it)}" } ?: "Your whole portfolio") }
                    EyeButton(vm)
                    PrimaryButton(if (syncing == "all") "Syncing" else "Sync all", busy = syncing == "all") { vm.syncAll() }
                }
            }
            if (all.isNotEmpty()) item { FilterBar(vm, all) }
            message?.let { item { Note(it) } }
            kite?.let { k ->
                item {
                    WvCard {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Outlined.WarningAmber, contentDescription = null, tint = Wv.c.warn)
                            Spacer(Modifier.width(8.dp))
                            Text("Kite needs a login. Authorize it to get live quotes and day changes.", style = Wv.sub, color = Wv.c.text, modifier = Modifier.weight(1f))
                        }
                        PrimaryButton("Authorize Kite") { openLink(context, k.auth_url.orEmpty()) }
                    }
                }
            }
            if (holdingsRes.loading && all.isEmpty()) item { Note("Loading your portfolio…") }
            holdingsRes.error?.takeIf { all.isEmpty() }?.let { e ->
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Note("Could not load your portfolio. $e", bad = true)
                        OutlinedButton(onClick = { vm.refreshAll() }, shape = RoundedCornerShape(10.dp)) { Text("Retry", color = Wv.c.text) }
                    }
                }
            }
            if (!holdingsRes.loading && holdingsRes.error == null && all.isEmpty()) {
                item {
                    WvCard {
                        Text("No holdings yet", style = Wv.title, color = Wv.c.text)
                        Text("Connect a broker and run a sync to see your portfolio here.", style = Wv.sub, color = Wv.c.text2)
                        OutlinedButton(onClick = onBrokers, shape = RoundedCornerShape(10.dp)) { Text("Connect a broker", color = Wv.c.accent) }
                    }
                }
            }
            if (all.isNotEmpty() && positions.isEmpty()) item { Note("Nothing matches these filters.") }

            if (positions.isNotEmpty()) {
                item { HeroCard(positions, totals, hist, period, filterActive) { period = it } }
                item { TodayTile(totals, nifty, dayCoverage(positions)) }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        TotalPnlTile(totals, Modifier.weight(1f))
                        MarketGainTile(hist, period, Modifier.weight(1f))
                    }
                }
                if (brief.isNotEmpty()) item { BriefCard(brief) }
                cards.chunked(2).forEach { pair ->
                    item(key = "cards-${pair.first().cls}") {
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            pair.forEach { c ->
                                ClassCardView(c, period, if (c.cls == "US_STOCKS") usdMove else null, Modifier.weight(1f)) {
                                    vm.classFilter.value = setOf(c.cls)
                                    onHoldings()
                                }
                            }
                            if (pair.size == 1) Box(Modifier.weight(1f))
                        }
                    }
                }
                item { DayMoveCard(cards, positions, totals.day, onStock) }
                item { SignalsPanelCard(dash, dashFailed, positions.any { it.cls == "EQUITY" || it.cls == "US_STOCKS" }, onSignals, onStock) }
                item { DriftCard(drift, targets.data.orEmpty().values.any { it > 0 }) { editTargets = true } }
                item { RiskCard(risk.data, conc, drawdown, usdPct) }
                item { NotesCard(notes) }
                item { LargestCard(positions, totals.cur, onStock, onHoldings) }
                item { ByBrokerCard(filtered, totals.cur, onBrokers) }
            }
        }
    }
    if (editTargets) {
        val classes = (cards.map { it.cls } + targets.data.orEmpty().keys).distinct()
        TargetsDialog(classes, targets.data.orEmpty(), onSave = { avm.saveTargets(it); editTargets = false }, onDismiss = { editTargets = false })
    }
}

// --- notes and the brief ------------------------------------------------------------------------------------

private fun overviewNotes(sessions: List<BrokerSession>, positions: List<Position>, totals: Totals, drift: List<DriftRow>, filtered: List<Holding>, targets: Map<String, Double>): List<Note2> {
    val out = mutableListOf<Note2>()
    sessions.filter { needsAttention(it) }.forEach { s ->
        out += Note2("s-${s.connection_id}", "neg", "${s.display_name.substringBefore(" — ")} needs attention", "It is ${s.status.replace('_', ' ').lowercase()}, so its holdings may be stale until you reconnect.")
    }
    positions.filter { totals.cur > 0 && it.cur / totals.cur * 100 >= SINGLE_POSITION_LIMIT_PCT }.take(2).forEach { p ->
        out += Note2("c-${p.key}", "warn", "${p.sym} is concentrated", "${weightPct(p.cur / totals.cur * 100)} of the portfolio, above the ${SINGLE_POSITION_LIMIT_PCT.toInt()}% single-position guide.")
    }
    drift.filter { it.target > 0 && abs(it.drift) >= 5 }.forEach { d ->
        out += Note2("d-${d.cls}", "warn", "${classLabel(d.cls)} has drifted", "${weightPct(d.weight)} of the portfolio against a ${d.target.toInt()}% target, ${String.format("%.1f", abs(d.drift))} points ${if (d.drift > 0) "over" else "under"}.")
    }
    filtered.mapNotNull { h -> dayPctOf(h)?.let { h to it } }.filter { abs(it.second) >= 5 }.sortedByDescending { abs(it.second) }.take(2).forEach { (h, p) ->
        out += Note2("m-${h.holding_id}", "info", "${displaySymbol(h)} moved ${pct(p)}", "Large move in the last session.")
    }
    if (filtered.isNotEmpty() && filtered.all { it.data_freshness != "live" }) {
        out += Note2("stale", "warn", "No live prices", "Every holding shows stored prices. Check the Kite session or run a sync.")
    }
    if (targets.isEmpty() && filtered.isNotEmpty()) out += Note2("no-targets", "info", "No target allocation set", "Set one to get drift notes when your mix moves away from plan.")
    if (out.isEmpty()) out += Note2("clear", "ok", "Nothing to flag", "Brokers are connected, no position is oversized and allocation is on target.")
    return out
}

private fun overviewBrief(totals: Totals, cards: List<ClassCard>, nifty: Double?, dash: DashSignals, drift: List<DriftRow>, conc: Concentration): List<String> {
    val out = mutableListOf<String>()
    if (totals.day != null && totals.dayPct != null) {
        val day = totals.day
        val dayPct = totals.dayPct
        val withDay = cards.filter { it.day != null }
        val worst = withDay.minByOrNull { it.day!! }
        val best = withDay.maxByOrNull { it.day!! }
        var line = "Your portfolio is ${if (day >= 0) "up" else "down"} ${String.format("%.2f", abs(dayPct))}% today (${signedCompact(day)})"
        if (nifty != null) line += ", ${if (dayPct - nifty >= 0) "ahead of" else "behind"} the Nifty (${pct(nifty)})"
        line += "."
        val hasWorst = worst != null && worst.day!! < 0
        if (hasWorst) line += " ${classLabel(worst!!.cls)} cost the most (${signedCompact(worst.day)})"
        if (best != null && best.day!! > 0 && best != worst) line += "${if (hasWorst) "," else ""} ${classLabel(best.cls)} helped most (${signedCompact(best.day)})"
        if (!line.endsWith(".")) line += "."
        out += line
    }
    if (dash.covered > 0) {
        val parts = mutableListOf<String>()
        val sellNames = dash.sells.map { it.src.name }.distinct().take(3)
        if (dash.sells.isNotEmpty()) parts += "${dash.sells.size} sell call${if (dash.sells.size == 1) "" else "s"} on your holdings this week" + if (sellNames.isNotEmpty()) " (${sellNames.joinToString(", ")})" else ""
        if (dash.buys.isNotEmpty()) parts += "${dash.buys.size} new buy${if (dash.buys.size == 1) "" else "s"}"
        if (dash.review.isNotEmpty()) parts += "${dash.review.size} to review"
        out += if (parts.isNotEmpty()) "Signals: ${parts.joinToString(", ")}." else "Signals: no sell calls on your holdings this week."
    }
    val guide = drift.filter { it.target > 0 && abs(it.drift) >= 3 }.maxByOrNull { abs(it.drift) }
    if (conc.top1 != null && conc.top1Pct >= SINGLE_POSITION_LIMIT_PCT) {
        out += "${conc.top1.sym} is ${weightPct(conc.top1Pct)} of the portfolio, above the ${SINGLE_POSITION_LIMIT_PCT.toInt()}% guide."
    } else if (guide != null) {
        out += "${classLabel(guide.cls)} sits ${String.format("%.1f", abs(guide.drift))} points ${if (guide.drift > 0) "over" else "under"} target."
    }
    return out
}

// --- hero, today, totals ------------------------------------------------------------------------------------

@Composable
private fun HeroCard(positions: List<Position>, totals: Totals, history: List<HistoryPoint>, period: Period, filterActive: Boolean, onPeriod: (Period) -> Unit) {
    val window = remember(history, period) { chartWindow(history, period) }
    WvCard {
        Text("Net worth" + if (filterActive) " · filtered" else "", style = Wv.small, color = Wv.c.text3)
        Text(compact(totals.cur), style = Wv.kpi, color = Wv.c.text)
        Text("${positions.size} holdings · ${compact(totals.inv)} invested", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
        Seg(Period.entries.map { it to it.label }, period, Modifier.fillMaxWidth()) { onPeriod(it) }
        if (window.size < 2) {
            Text("The chart appears once there are two daily snapshots. Each sync adds one.", style = Wv.sub, color = Wv.c.text3)
        } else {
            LineChart(
                window.map { it.date },
                listOf(Series("Value", Wv.c.accent, window.map { it.value }), Series("Invested", Wv.c.text3, window.map { it.invested }, dashed = true)),
                format = { compact(it) },
                height = 170.dp,
            )
        }
    }
}

/** A proportion bar: the fraction is filled in the given colour. */
@Composable
private fun Bar(fraction: Double, color: Color, modifier: Modifier = Modifier, height: Int = 6) {
    Box(modifier.height(height.dp).clip(RoundedCornerShape(3.dp)).background(Wv.c.surface2)) {
        Box(Modifier.fillMaxWidth(fraction.toFloat().coerceIn(0f, 1f)).fillMaxHeight().clip(RoundedCornerShape(3.dp)).background(color))
    }
}

@Composable
private fun TodayTile(totals: Totals, nifty: Double?, coverage: DayCoverage) {
    WvCard {
        Text("Today's P&L", style = Wv.small, color = Wv.c.text3)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(signedCompact(totals.day), style = Wv.kpi, color = toneOf(totals.day))
            totals.dayPct?.let { Badge(pct(it), if (it < 0) Tone.Bad else Tone.Ok) }
        }
        if (nifty != null && totals.dayPct != null) {
            val scale = maxOf(abs(totals.dayPct), abs(nifty), 0.01)
            listOf(Triple("You", totals.dayPct, if (totals.dayPct < 0) Wv.c.loss else Wv.c.gain), Triple("Nifty", nifty, Wv.c.text3)).forEach { (who, v, color) ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(who, style = Wv.small, color = Wv.c.text2, modifier = Modifier.width(48.dp))
                    Bar(abs(v) / scale, color, Modifier.weight(1f))
                    Text(pct(v), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text2, modifier = Modifier.padding(start = 8.dp).width(64.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
                }
            }
            val vs = totals.dayPct - nifty
            Text("${if (vs >= 0) "Ahead of" else "Behind"} the Nifty by ${String.format("%.2f", abs(vs))}%", style = Wv.small, color = Wv.c.text3)
        }
        CoverageNote(coverage)
    }
}

/** "All 24 reporting", or how many report a 1-day change and, on a tap, which do not and why. */
@Composable
fun CoverageNote(cov: DayCoverage) {
    var open by remember { mutableStateOf(false) }
    if (cov.missing.isEmpty()) {
        Text("All ${cov.total} reporting", style = Wv.small, color = Wv.c.text3)
        return
    }
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { open = true }) {
        Text("${cov.reporting} of ${cov.total} reporting", style = Wv.small, color = Wv.c.text3)
        Spacer(Modifier.width(4.dp))
        Icon(Icons.Outlined.Info, contentDescription = "Which holdings have no 1-day change", tint = Wv.c.text3, modifier = Modifier.size(14.dp))
    }
    if (open) {
        AlertDialog(
            onDismissRequest = { open = false },
            containerColor = Wv.c.surface,
            title = { Text("${cov.missing.size} holdings have no 1-day change", color = Wv.c.text) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    cov.reasons.forEach { Text(it, style = Wv.sub, color = Wv.c.text2) }
                    Text(cov.missing.take(8).joinToString(", ") { it.sym } + if (cov.missing.size > 8) " and ${cov.missing.size - 8} more" else "", style = Wv.small, color = Wv.c.text3)
                    Text("Their change is left out of the 1-day total rather than counted as zero.", style = Wv.small, color = Wv.c.text3)
                }
            },
            confirmButton = { TextButton(onClick = { open = false }) { Text("Close", color = Wv.c.accent) } },
        )
    }
}

@Composable
private fun TotalPnlTile(totals: Totals, modifier: Modifier) {
    WvCard(modifier) {
        Text("Total P&L", style = Wv.small, color = Wv.c.text3)
        Text(signedCompact(totals.pnl), style = Wv.title.copy(fontFeatureSettings = "tnum"), color = toneOf(totals.pnl))
        totals.pnlPct?.let { Badge(pct(it), if (it < 0) Tone.Bad else Tone.Ok) }
        Text("on ${compact(totals.inv)} invested", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
    }
}

@Composable
private fun MarketGainTile(history: List<HistoryPoint>, period: Period, modifier: Modifier) {
    val from = baseline(history, if (period == Period.D1) Period.M1 else period)
    val last = history.lastOrNull()
    val gain = if (from != null && last != null) last.value - from.value - (last.invested - from.invested) else null
    val gainPct = if (from != null && gain != null && from.value > 0) gain / from.value * 100 else null
    val added = if (from != null && last != null) last.invested - from.invested else null
    WvCard(modifier) {
        Text("Market gain · ${if (period == Period.D1) "last month" else period.long}", style = Wv.small, color = Wv.c.text3)
        Text(signedCompact(gain), style = Wv.title.copy(fontFeatureSettings = "tnum"), color = toneOf(gain))
        gainPct?.let { Badge(pct(it), if (it < 0) Tone.Bad else Tone.Ok) }
        Text(
            if (from != null) "since ${shortDate(from.date)}" + (added?.takeIf { abs(it) >= 1 }?.let { " · ${signedCompact(it)} money added, not counted" } ?: "") else "needs a few daily snapshots",
            style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3,
        )
    }
}

@Composable
private fun BriefCard(lines: List<String>) {
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.AutoAwesome, contentDescription = null, tint = Wv.c.accent, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Text("Today in brief", style = Wv.title, color = Wv.c.text)
        }
        lines.forEach { l ->
            Row {
                Text("•", style = Wv.sub, color = Wv.c.text3, modifier = Modifier.width(14.dp))
                Text(l, style = Wv.sub, color = Wv.c.text2)
            }
        }
    }
}

// --- a card per asset class ------------------------------------------------------------------------------------

@Composable
fun Sparkline(values: List<Double>, color: Color, modifier: Modifier = Modifier) {
    if (values.size < 2) {
        Box(modifier.fillMaxWidth().height(30.dp))
        return
    }
    val lo = values.min()
    val span = (values.max() - lo).takeIf { it > 0 } ?: 1.0
    Canvas(modifier.fillMaxWidth().height(30.dp)) {
        val w = size.width
        val h = size.height
        val pts = values.mapIndexed { i, v -> Offset(w * i / (values.size - 1), (h - ((v - lo) / span) * (h - 4) - 2).toFloat()) }
        val area = Path().apply { moveTo(0f, h); pts.forEach { lineTo(it.x, it.y) }; lineTo(w, h); close() }
        drawPath(area, color.copy(alpha = 0.10f))
        val line = Path().apply { pts.forEachIndexed { i, p -> if (i == 0) moveTo(p.x, p.y) else lineTo(p.x, p.y) } }
        drawPath(line, color, style = Stroke(width = 1.8.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
    }
}

@Composable
private fun ClassCardView(c: ClassCard, period: Period, usdMove: Double?, modifier: Modifier, onOpen: () -> Unit) {
    val color = classColor(c.cls)
    WvCard(modifier.clickable(onClick = onOpen), padding = 12) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).clip(CircleShape).background(color))
            Spacer(Modifier.width(6.dp))
            Text(classLabel(c.cls), style = Wv.small.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text, modifier = Modifier.weight(1f), maxLines = 2)
            Text(weightPct(c.weight), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
        }
        Text(compact(c.cur), style = Wv.title.copy(fontFeatureSettings = "tnum"), color = Wv.c.text)
        Bar(c.weight / 100, color, Modifier.fillMaxWidth(), height = 4)
        // label above, amount and percentage on one line that wraps if needed: two side-by-side columns
        // ran their numbers into each other on narrow phones and with large text
        CardFigure("Total P&L", signedCompact(c.pnl), pct(c.pnlPct), toneOf(c.pnl))
        CardFigure("1-day", if (c.day == null) "—" else signedCompact(c.day), if (c.day == null) "no feed" else pct(c.dayPct), toneOf(c.day))
        Sparkline(c.spark, color)
        if (period != Period.D1) Text("${period.label}: ${if (c.change == null) "—" else signedCompact(c.change)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(c.change))
        if (usdMove != null) Text("${pct(usdMove)} in USD today", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
        c.best?.let { Text("▲ ${it.sym}", style = Wv.small, color = Wv.c.gain, maxLines = 1, overflow = TextOverflow.Ellipsis) }
        c.worst?.let { Text("▼ ${it.sym}", style = Wv.small, color = Wv.c.loss, maxLines = 1, overflow = TextOverflow.Ellipsis) }
    }
}

@Composable
private fun CardFigure(label: String, amount: String, pctText: String, tone: Color) {
    Column {
        Text(label, style = Wv.small, color = Wv.c.text3)
        Text(
            androidx.compose.ui.text.buildAnnotatedString {
                withStyle(androidx.compose.ui.text.SpanStyle(fontWeight = FontWeight.SemiBold)) { append(amount) }
                append("  ")
                append(pctText)
            },
            style = Wv.small.copy(fontFeatureSettings = "tnum"), color = tone,
        )
    }
}

// --- why today moved ---------------------------------------------------------------------------------------------

@Composable
private fun DayMoveCard(cards: List<ClassCard>, positions: List<Position>, total: Double?, onStock: (String) -> Unit) {
    val rows = cards.filter { it.day != null }.sortedByDescending { abs(it.day!!) }
    val max = rows.maxOfOrNull { abs(it.day!!) }?.coerceAtLeast(1.0) ?: 1.0
    val ranked = positions.filter { it.day != null }.sortedByDescending { it.day!! }
    val up = ranked.filter { it.day!! > 0 }.take(5)
    val down = ranked.filter { it.day!! < 0 }.reversed().take(5)
    val byPct = positions.filter { it.dayPct != null }.sortedByDescending { it.dayPct!! }
    val pctUp = byPct.filter { it.dayPct!! > 0 }.take(4)
    val pctDown = byPct.filter { it.dayPct!! < 0 }.reversed().take(4)
    WvCard {
        Text("Why today moved", style = Wv.title, color = Wv.c.text)
        Text(if (total == null) "No day change reported yet" else "${signedCompact(total)} in total, by asset class and by holding", style = Wv.small, color = Wv.c.text3)
        if (rows.isEmpty()) Text("No asset class has reported a 1-day change yet.", style = Wv.sub, color = Wv.c.text3)
        rows.forEach { r ->
            val neg = r.day!! < 0
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 2.dp)) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(classColor(r.cls)))
                Spacer(Modifier.width(6.dp))
                Text(classLabel(r.cls), style = Wv.small, color = Wv.c.text2, modifier = Modifier.width(92.dp), maxLines = 1, overflow = TextOverflow.Ellipsis)
                // a centred axis: losses grow left of the middle, gains right
                BoxWithConstraints(Modifier.weight(1f).height(10.dp)) {
                    val half = maxWidth / 2
                    val len = half * (abs(r.day) / max).toFloat()
                    Box(Modifier.offset(x = half - 0.5.dp).width(1.dp).fillMaxHeight().background(Wv.c.borderStrong))
                    Box(
                        Modifier.offset(x = if (neg) half - len else half).width(len).fillMaxHeight().clip(RoundedCornerShape(2.dp))
                            .background(if (neg) Wv.c.loss else Wv.c.gain),
                    )
                }
                Text(signedCompact(r.day), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(r.day), modifier = Modifier.padding(start = 8.dp).width(84.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
            }
        }
        // one list under another: side by side, long fund names ran into their amounts on a phone
        Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(top = 6.dp)) {
            MoverList("Lifted the day", up, Wv.c.gain, "Nothing gained", Modifier.fillMaxWidth(), onStock) { signedCompact(it.day) }
            MoverList("Pulled it down", down, Wv.c.loss, "Nothing lost", Modifier.fillMaxWidth(), onStock) { signedCompact(it.day) }
            MoverList("Biggest % gains", pctUp, Wv.c.gain, "None", Modifier.fillMaxWidth(), onStock) { pct(it.dayPct) }
            MoverList("Biggest % falls", pctDown, Wv.c.loss, "None", Modifier.fillMaxWidth(), onStock) { pct(it.dayPct) }
        }
    }
}

@Composable
private fun MoverList(title: String, items: List<Position>, tone: Color, empty: String, modifier: Modifier, onStock: (String) -> Unit, value: (Position) -> String) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(title.uppercase(), style = Wv.over, color = tone)
        if (items.isEmpty()) Text(empty, style = Wv.small, color = Wv.c.text3)
        items.forEach { p ->
            Row(Modifier.fillMaxWidth().then(p.stockSymbol?.let { s -> Modifier.clickable { onStock(s) } } ?: Modifier).padding(vertical = 3.dp)) {
                Text(p.sym, style = Wv.sub, color = Wv.c.text, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(value(p), style = Wv.sub.copy(fontFeatureSettings = "tnum", fontWeight = FontWeight.SemiBold), color = tone, modifier = Modifier.padding(start = 12.dp))
            }
        }
    }
}

// --- signals on your holdings --------------------------------------------------------------------------------------

@Composable
private fun SignalsPanelCard(d: DashSignals, failed: Boolean, hasStocks: Boolean, onSignals: (SignalsPreset) -> Unit, onStock: (String) -> Unit) {
    if (!hasStocks) return
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Signals on your holdings", style = Wv.title, color = Wv.c.text)
                Text("Swing V2.1 and ATH breakout calls, on live prices", style = Wv.small, color = Wv.c.text3)
            }
            TextButton(onClick = { onSignals(SignalsPreset(source = "held")) }) { Text("Open", color = Wv.c.accent) }
        }
        if (failed || d.covered == 0) {
            Text(if (failed) "Signals could not be loaded." else "No signals saved yet. Press Refresh Momentum Stocks on the Signals tab once.", style = Wv.sub, color = Wv.c.text3)
            return@WvCard
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SignalTile("${d.sells.size}", "Sell calls · 7 sessions", if (d.sells.isNotEmpty()) Wv.c.loss else Wv.c.text, Modifier.weight(1f)) { onSignals(d.sellsPreset) }
            SignalTile("${d.buys.size}", "New buys · 2 sessions", Wv.c.gain, Modifier.weight(1f)) { onSignals(d.buysPreset) }
            SignalTile("${d.review.size}", "To review", if (d.review.isNotEmpty()) Wv.c.warn else Wv.c.text, Modifier.weight(1f)) { onSignals(d.reviewPreset) }
        }
        if (!d.hasExit) Text("Sell history is added after the next signals refresh.", style = Wv.small, color = Wv.c.text3)
        if (d.review.isNotEmpty()) {
            Text(
                "To review (all three signals bearish): " + d.review.take(6).joinToString(", ") { it.name } + if (d.review.size > 6) " and ${d.review.size - 6} more" else "",
                style = Wv.small, color = Wv.c.text2,
            )
        }
        Text("SELL CALLS", style = Wv.over, color = Wv.c.loss, modifier = Modifier.clickable { onSignals(d.sellsPreset) }.padding(top = 4.dp))
        if (d.sells.isEmpty()) Text("No sell calls on your holdings in the last 7 sessions.", style = Wv.small, color = Wv.c.text3)
        val open = { r: CallRow -> if (r.src.code !in d.usCodes) onStock(r.src.sig?.instrument?.ifBlank { null } ?: r.src.code) }
        d.sells.take(4).forEach { r -> CallLine(r, open, "${weekdayDate(r.date)} · ${r.tail.ifBlank { r.why }}", r.tailTone) }
        Text("NEW BUYS", style = Wv.over, color = Wv.c.gain, modifier = Modifier.clickable { onSignals(d.buysPreset) }.padding(top = 4.dp))
        if (d.buys.isEmpty()) Text("No new buys on your holdings in the last 2 sessions.", style = Wv.small, color = Wv.c.text3)
        d.buys.take(3).forEach { r -> CallLine(r, open, "${weekdayDate(r.date)} · ${r.why}", r.sinceRef?.abs) }
    }
}

@Composable
private fun SignalTile(value: String, label: String, tone: Color, modifier: Modifier, onClick: () -> Unit) {
    Column(
        modifier.clip(RoundedCornerShape(10.dp)).background(Wv.c.surface2).clickable(onClick = onClick).padding(10.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(value, style = Wv.title.copy(fontFeatureSettings = "tnum"), color = tone)
        Text(label, style = Wv.small, color = Wv.c.text2, maxLines = 2)
    }
}

@Composable
private fun CallLine(r: CallRow, onOpen: (CallRow) -> Unit, sub: String, subTone: Double?) {
    Column(Modifier.fillMaxWidth().clickable { onOpen(r) }) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(r.src.name, style = Wv.sub, color = Wv.c.text, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
            Badge(if (r.kind == Kind.Swing) "Swing" else "ATH", if (r.kind == Kind.Swing) Tone.Info else Tone.Ok)
            if (r.waiting) Badge("Waiting", Tone.Warn)
        }
        Text(sub, style = Wv.small, color = if (subTone != null) toneOf(subTone) else Wv.c.text3, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

// --- allocation against targets -------------------------------------------------------------------------------------

@Composable
private fun DriftCard(rows: List<DriftRow>, hasTargets: Boolean, onEdit: () -> Unit) {
    val max = rows.maxOfOrNull { maxOf(it.weight, it.target) }?.coerceAtLeast(1.0) ?: 1.0
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Allocation and targets", style = Wv.title, color = Wv.c.text)
                Text(if (hasTargets) "Weight against target, and what closes the gap" else "Set targets to see how far each class has drifted", style = Wv.small, color = Wv.c.text3)
            }
            OutlinedButton(onClick = onEdit, shape = RoundedCornerShape(10.dp)) { Text(if (hasTargets) "Edit targets" else "Set targets", color = Wv.c.text) }
        }
        MixBar(rows.filter { it.weight > 0 }.map { classColorStatic(it.cls) to it.weight })
        rows.forEach { r ->
            val color = classColor(r.cls)
            Column(Modifier.padding(vertical = 3.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(10.dp).clip(CircleShape).background(color))
                    Spacer(Modifier.width(8.dp))
                    Text(classLabel(r.cls), style = Wv.body, color = Wv.c.text, modifier = Modifier.weight(1f))
                    Text(weightPct(r.weight) + if (r.target > 0) " / ${r.target.toInt()}%" else "", style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                    Text(
                        when {
                            r.target <= 0 -> "—"
                            abs(r.move) < 1000 -> "on target"
                            else -> "${if (r.move > 0) "Add" else "Trim"} ${compact(abs(r.move))}"
                        },
                        style = Wv.small.copy(fontFeatureSettings = "tnum", fontWeight = FontWeight.SemiBold),
                        color = if (r.target > 0 && abs(r.move) >= 1000) toneOf(r.move) else Wv.c.text3,
                        textAlign = androidx.compose.ui.text.style.TextAlign.End,
                        modifier = Modifier.width(96.dp),
                    )
                }
                if (hasTargets) {
                    BoxWithConstraints(Modifier.fillMaxWidth().padding(top = 4.dp, start = 18.dp).height(8.dp)) {
                        Box(Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)).background(Wv.c.surface2))
                        Box(Modifier.fillMaxWidth((r.weight / max).toFloat().coerceIn(0f, 1f)).height(6.dp).clip(RoundedCornerShape(3.dp)).background(color))
                        if (r.target > 0) Box(Modifier.offset(x = maxWidth * (r.target / max).toFloat().coerceIn(0f, 1f) - 1.dp).width(2.dp).fillMaxHeight().background(Wv.c.text))
                    }
                }
            }
        }
        if (hasTargets) Text("Add and Trim are rupees at today's total. Selling to rebalance can trigger tax, so treat it as a guide.", style = Wv.small, color = Wv.c.text3)
    }
}

/** The fixed class colours outside composition (the mix bar takes plain colours). */
private fun classColorStatic(cls: String): Color = LightWv.classColors[cls] ?: Color(0xFFA3ADBB)

// --- risk and concentration -------------------------------------------------------------------------------------------

@Composable
private fun RiskCard(data: RiskResponse?, conc: Concentration, drawdown: Drawdown?, usdPct: Double) {
    val r = data?.risk
    WvCard {
        Text("Risk", style = Wv.title, color = Wv.c.text)
        Text("How your Indian stocks would have behaved at today's weights", style = Wv.small, color = Wv.c.text3)
        if (r == null) {
            Text(
                if (data != null) "Beta and volatility need stored price history for your stocks (${data.measured_stocks} of ${data.total_stocks} have it). Press Refresh Momentum Stocks on the Signals tab once."
                else "Risk figures are not available right now.",
                style = Wv.sub, color = Wv.c.text3,
            )
        } else {
            val varRupees = r.var95_1d_pct / 100 * data.equity_value
            StatLine("Beta vs Nifty", r.beta?.let { String.format("%.2f", it) } ?: "—", note = r.beta?.let { if (it > 1.05) "moves more than the market" else if (it < 0.95) "moves less than the market" else "moves with the market" })
            StatLine("Volatility", String.format("%.1f%%", r.volatility_pct), note = String.format("Nifty %.1f%% a year", r.benchmark_volatility_pct))
            StatLine("1-day loss, 95% of days", String.format("−%.2f%%", r.var95_1d_pct), Wv.c.loss, "about ${compact(varRupees)} on your stocks")
            StatLine("Worst fall from a peak", String.format("%.1f%%", r.max_drawdown_pct).replace("-", "−"), Wv.c.loss, "over ${r.days} trading days")
            StatLine("Best / worst day", "${pct(r.best_day_pct)} / ${pct(r.worst_day_pct)}", note = String.format("%.0f%% of days were up", r.positive_days_pct))
            StatLine("Move with the market", r.correlation?.let { String.format("%.2f", it) } ?: "—", note = "1.0 = identical to the Nifty")
            if (r.coverage_pct < 100) Text(String.format("Measured on %.0f%% of your Indian stock value (%d of %d stocks).", r.coverage_pct, data.measured_stocks, data.total_stocks), style = Wv.small, color = Wv.c.text3)
            if (r.high_beta.isNotEmpty()) Text("Highest beta: " + r.high_beta.joinToString(", ") { String.format("%s %.1f", it.name, it.beta) } + ".", style = Wv.small, color = Wv.c.text3)
        }
        Text("CONCENTRATION", style = Wv.over, color = Wv.c.text3, modifier = Modifier.padding(top = 6.dp))
        ConcRow("Largest position", conc.top1Pct, conc.top1?.sym, SINGLE_POSITION_LIMIT_PCT, 40.0)
        ConcRow("Top 5", conc.top5Pct, null, null, 100.0)
        ConcRow("Top 10", conc.top10Pct, null, null, 100.0)
        ConcRow("US dollar exposure", usdPct, null, null, 100.0)
        drawdown?.let { d ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Down from peak", style = Wv.small, color = Wv.c.text2, modifier = Modifier.width(132.dp))
                Bar(abs(d.current) * 4 / 100, Wv.c.loss, Modifier.weight(1f))
                Text(pct(d.current, 1), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(d.current), modifier = Modifier.padding(start = 8.dp).width(56.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
            }
        }
    }
}

@Composable
private fun ConcRow(label: String, value: Double, name: String?, limit: Double?, scale: Double) {
    val over = limit != null && value > limit
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.width(132.dp)) {
            Text(label, style = Wv.small, color = Wv.c.text2)
            name?.let { Text(it, style = Wv.small, color = Wv.c.text3, maxLines = 1, overflow = TextOverflow.Ellipsis) }
        }
        BoxWithConstraints(Modifier.weight(1f).height(6.dp)) {
            Bar(value / scale, if (over) Wv.c.warn else Wv.c.accent, Modifier.fillMaxWidth())
            if (limit != null) Box(Modifier.offset(x = maxWidth * (limit / scale).toFloat() - 1.dp).width(2.dp).fillMaxHeight().background(Wv.c.text))
        }
        Text(weightPct(value), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = if (over) Wv.c.loss else Wv.c.text2, modifier = Modifier.padding(start = 8.dp).width(56.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
    }
}

// --- notes, largest positions, by broker -------------------------------------------------------------------------------

@Composable
private fun NotesCard(notes: List<Note2>) {
    WvCard {
        Text("Notes", style = Wv.title, color = Wv.c.text)
        Text("Computed from your holdings and connections", style = Wv.small, color = Wv.c.text3)
        notes.forEach { n ->
            val (icon, tint) = when (n.tone) {
                "ok" -> Icons.Outlined.CheckCircle to Wv.c.gain
                "info" -> Icons.Outlined.Info to Wv.c.accent
                "neg" -> Icons.Outlined.WarningAmber to Wv.c.loss
                else -> Icons.Outlined.WarningAmber to Wv.c.warn
            }
            Row(verticalAlignment = Alignment.Top, modifier = Modifier.padding(vertical = 3.dp)) {
                Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(18.dp).padding(top = 1.dp))
                Spacer(Modifier.width(8.dp))
                Column {
                    Text(n.title, style = Wv.sub.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                    Text(n.body, style = Wv.small, color = Wv.c.text2)
                }
            }
        }
    }
}

@Composable
private fun LargestCard(positions: List<Position>, total: Double, onStock: (String) -> Unit, onHoldings: () -> Unit) {
    val top = positions.sortedByDescending { it.cur }.take(6)
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Largest positions", style = Wv.title, color = Wv.c.text)
                Text("Merged across brokers, share of portfolio value", style = Wv.small, color = Wv.c.text3)
            }
            TextButton(onClick = onHoldings) { Text("All holdings", color = Wv.c.accent) }
        }
        top.forEachIndexed { i, p ->
            val w = if (total > 0) p.cur / total * 100 else 0.0
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().then(p.stockSymbol?.let { s -> Modifier.clickable { onStock(s) } } ?: Modifier).padding(vertical = 3.dp)) {
                Text("${i + 1}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3, modifier = Modifier.width(18.dp))
                Column(Modifier.weight(1f)) {
                    Text(p.sym, style = Wv.sub, color = Wv.c.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(6.dp).clip(CircleShape).background(classColor(p.cls)))
                        Spacer(Modifier.width(4.dp))
                        Text("${classLabel(p.cls)} · ${p.brokers.joinToString(" + ") { brokerKeyLabel(it) }}", style = Wv.small, color = Wv.c.text3, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                Bar(minOf(1.0, w * 4 / 100), Wv.c.accent, Modifier.width(60.dp))
                Text(weightPct(w), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text2, modifier = Modifier.padding(start = 8.dp).width(48.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
            }
        }
    }
}

@Composable
private fun ByBrokerCard(filtered: List<Holding>, total: Double, onBrokers: () -> Unit) {
    data class B(val key: String, val cur: Double, val inv: Double, val count: Int)
    val rows = filtered.groupBy { brokerKeyOf(it.connection_id) }.map { (k, hs) -> B(k, hs.sumOf { it.current_value }, hs.sumOf { it.invested }, hs.size) }.sortedByDescending { it.cur }
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("By broker", style = Wv.title, color = Wv.c.text)
                Text("Holdings value at each account", style = Wv.small, color = Wv.c.text3)
            }
            TextButton(onClick = onBrokers) { Text("Manage", color = Wv.c.accent) }
        }
        rows.forEach { b ->
            val w = if (total > 0) b.cur / total * 100 else 0.0
            val ret = if (b.inv > 0) (b.cur - b.inv) / b.inv * 100 else null
            val color = BROKER_COLORS[b.key] ?: Wv.c.text3
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 3.dp)) {
                Box(Modifier.size(28.dp).clip(RoundedCornerShape(7.dp)).background(color), contentAlignment = Alignment.Center) {
                    Text(brokerKeyLabel(b.key).take(1), style = Wv.small.copy(fontWeight = FontWeight.Bold), color = Color.White)
                }
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(brokerKeyLabel(b.key), style = Wv.sub, color = Wv.c.text)
                    Text("${b.count} holdings · ${weightPct(w)} of total", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
                    Bar(w / 100, color, Modifier.fillMaxWidth().padding(top = 3.dp), height = 4)
                }
                Column(horizontalAlignment = Alignment.End, modifier = Modifier.padding(start = 10.dp)) {
                    Text(compact(b.cur), style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                    Text(pct(ret, 1), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(ret))
                }
            }
        }
    }
}

// --- the eye switch and the filters (shared by the Overview and Holdings) -------------------------------------------------

/** Hide or show every rupee amount (the web's eye button); the phone remembers the choice. */
@Composable
fun EyeButton(vm: AppViewModel) {
    val hidden = Privacy.hidden
    androidx.compose.material3.IconButton(onClick = { vm.setHideAmounts(!hidden) }) {
        Icon(
            if (hidden) Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility,
            contentDescription = if (hidden) "Show amounts" else "Hide amounts",
            tint = Wv.c.text2,
        )
    }
}

/** Broker and asset-class filters, each a multi-select; "All" clears it. */
@Composable
fun FilterBar(vm: AppViewModel, holdings: List<Holding>, showClasses: Boolean = true, trailing: @Composable () -> Unit = {}) {
    val brokers by vm.brokerFilter.collectAsState()
    val classes by vm.classFilter.collectAsState()
    var open by remember { mutableStateOf<String?>(null) }
    val positions = remember(holdings) { buildPositions(holdings) }
    val brokerCounts = remember(holdings) { holdings.groupBy { brokerKeyOf(it.connection_id) }.mapValues { it.value.size }.toSortedMap() }
    val classCounts = remember(positions) { CLASS_ORDER.mapNotNull { c -> positions.count { it.cls == c }.takeIf { it > 0 }?.let { c to it } } }
    // scrolls sideways rather than squeezing when the labels get long ("Asset class: Mutual funds")
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        Chip("Broker: " + when (brokers.size) { 0 -> "All"; 1 -> brokerKeyLabel(brokers.first()); else -> "${brokers.size}" } + " ▾", brokers.isNotEmpty()) { open = "broker" }
        if (showClasses) Chip("Asset class: " + when (classes.size) { 0 -> "All"; 1 -> classLabel(classes.first()); else -> "${classes.size}" } + " ▾", classes.isNotEmpty()) { open = "class" }
        if (brokers.isNotEmpty() || (showClasses && classes.isNotEmpty())) TextButton(onClick = { vm.brokerFilter.value = emptySet(); if (showClasses) vm.classFilter.value = emptySet() }) { Text("Reset", color = Wv.c.text2) }
        trailing()
    }
    open?.let { which ->
        val options = if (which == "broker") brokerCounts.map { (k, n) -> Triple(k, brokerKeyLabel(k), n) } else classCounts.map { (c, n) -> Triple(c, classLabel(c), n) }
        val target = if (which == "broker") vm.brokerFilter else vm.classFilter
        val selected = if (which == "broker") brokers else classes
        AlertDialog(
            onDismissRequest = { open = null },
            containerColor = Wv.c.surface,
            title = { Text(if (which == "broker") "Brokers" else "Asset classes", color = Wv.c.text) },
            text = {
                Column {
                    FilterOption("All", null, selected.isEmpty()) { target.value = emptySet() }
                    options.forEach { (value, label, n) ->
                        FilterOption(label, n, selected.isEmpty() || value in selected) {
                            val base = if (selected.isEmpty()) options.map { it.first }.toSet() else selected
                            val next = if (value in base) base - value else base + value
                            target.value = if (next.size == options.size) emptySet() else next
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { open = null }) { Text("Done", color = Wv.c.accent) } },
        )
    }
}

@Composable
private fun FilterOption(label: String, count: Int?, checked: Boolean, onToggle: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().clickable(onClick = onToggle)) {
        androidx.compose.material3.Checkbox(checked, { onToggle() }, colors = androidx.compose.material3.CheckboxDefaults.colors(checkedColor = Wv.c.accent, uncheckedColor = Wv.c.text3))
        Text(label, style = Wv.body, color = Wv.c.text, modifier = Modifier.weight(1f))
        count?.let { Text("$it", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3) }
    }
}

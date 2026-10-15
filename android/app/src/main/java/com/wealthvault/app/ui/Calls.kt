package com.wealthvault.app.ui

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.wealthvault.app.data.StockSignals

/**
 * The strategies' buy and sell calls (web/src/components/signals/NewCalls.tsx): trades they entered or left in
 * the latest sessions, grouped by strategy and day, with why each fired and how it has done since.
 */

data class CallSource(
    val code: String,
    val name: String,
    val sector: String? = null,
    val held: Boolean = false,
    val isNew: Boolean = false,
    val sig: StockSignals?,
    val ltp: Double,
)

enum class Kind(val title: String, val sub: String) {
    Swing("Swing V2.1", "UT Bot buy inside a 200-SMA uptrend; fills at the next open."),
    Ath("200-DMA ATH breakout", "Close above the all-time high shortly after a 200-DMA reclaim; bought at that close."),
}

/** 2, 7 or 0 for "every position open now" */
typealias BuyWindow = Int

const val OPEN_WINDOW: BuyWindow = 0

data class CallRow(
    val key: String,
    val src: CallSource,
    val kind: Kind,
    val date: String,
    val waiting: Boolean,
    val live: Boolean,
    val price: Double?,
    val priceNote: String,
    val why: String,
    val detail: String,
    val tail: String,
    val tailTone: Double? = null,
    val sinceRef: Since?,
)

/** The most recent `n` sessions seen across all stocks (each stock reports its own). */
fun latestSessions(sources: List<CallSource>, n: Int): List<String> =
    sources.flatMap { it.sig?.last_sessions.orEmpty() }.toSortedSet().toList().takeLast(n)

fun buildBuys(sources: List<CallSource>, sessions: List<String>, window: BuyWindow, fmt: PriceFmt, sessionOpen: Boolean): List<CallRow> {
    val out = mutableListOf<CallRow>()
    val inWindow = { d: String? -> d != null && (window == OPEN_WINDOW || d in sessions) }
    sources.forEach { src ->
        val sig = src.sig
        val s = sig?.swing
        val sc = s?.call
        if (s != null && sc != null) {
            val waiting = sc.queued && s.pending_order == "BUY"
            val open = !sc.queued && sc.entry_date != null && s.state == "IN_POSITION" && s.entry_date == sc.entry_date
            if (waiting || (open && inWindow(sc.entry_date))) {
                val entry = if (waiting) sc.signal_close else sc.entry_price
                out += CallRow(
                    key = "${src.code}-swing", src = src, kind = Kind.Swing,
                    date = if (waiting) sc.signal_date else sc.entry_date!!,
                    waiting = waiting,
                    live = sessionOpen && waiting && sc.signal_date == sig.live_date,
                    price = entry,
                    priceNote = if (waiting) "indicative" else "signal ${shortDate(sc.signal_date)}",
                    why = "UT Bot buy at the ${shortDate(sc.signal_date)} close, ${fmt.price(sc.signal_close)}",
                    detail = "Close ${signed1(sc.above_slow_pct)} over the 200-SMA; 50-SMA ${signed1(sc.fast_over_slow_pct)} over it; 200-SMA ${signed1(sc.slow_slope_pct)} in ${sc.slope_lookback ?: "—"} bars",
                    tail = when {
                        waiting -> "Stop is set when it fills"
                        sc.stop != null -> "Stop ${fmt.price(sc.stop)}" + (sc.stop_pct?.let { ", ${weight1(it)} below entry" } ?: "")
                        else -> "No protective stop"
                    },
                    sinceRef = since(entry, src.ltp),
                )
            }
        }
        val a = sig?.ath
        val ac = a?.call
        if (a != null && ac != null && a.state == "IN_POSITION" && a.entry_date == ac.entry_date && inWindow(ac.entry_date)) {
            out += CallRow(
                key = "${src.code}-ath", src = src, kind = Kind.Ath, date = ac.entry_date, waiting = false,
                live = sessionOpen && ac.entry_date == sig.live_date,
                price = ac.entry_price, priceNote = "at the close",
                why = "Closed ${fmt.price(ac.close)}, ${signed1(ac.above_ath_pct)} over the prior all-time high ${fmt.price(ac.prior_ath)}",
                detail = if (ac.days_since_below_dma != null) "${ac.days_since_below_dma} trading days after a close under the 200-DMA (window ${ac.window_bars ?: "—"})"
                else "Inside the ${ac.window_bars ?: "—"}-day window after a 200-DMA break",
                tail = if (ac.dma != null && ac.close != null && ac.close > 0) "Exit under the 200-DMA ${fmt.price(ac.dma)}, ${weight1((ac.dma / ac.close - 1) * 100)} below" else "Exit on a close under the 200-DMA",
                sinceRef = since(ac.entry_price, src.ltp),
            )
        }
    }
    return out.sortedWith(compareByDescending<CallRow> { it.date }.thenBy { it.src.name })
}

fun buildSells(sources: List<CallSource>, sessions: List<String>, fmt: PriceFmt, sessionOpen: Boolean): List<CallRow> {
    val out = mutableListOf<CallRow>()
    val ended = { entryDate: String, entryPrice: Double?, exitPrice: Double?, pnl: Double? ->
        "Bought ${shortDate(entryDate)} at ${fmt.price(entryPrice)}, sold ${fmt.price(exitPrice)}" + (pnl?.let { " (${signed1(it)})" } ?: "")
    }
    sources.forEach { src ->
        val sig = src.sig
        sig?.swing?.exits?.forEachIndexed { i, e ->
            if (e.exit_date !in sessions) return@forEachIndexed
            val stop = e.reason == "ATR STOP"
            out += CallRow(
                key = "${src.code}-swing-exit-$i", src = src, kind = Kind.Swing, date = e.exit_date, waiting = false, live = false,
                price = e.exit_price, priceNote = if (stop) "stop hit" else "at the open",
                why = if (stop) "Protective ATR stop hit on ${shortDate(e.exit_date)}" else "UT Bot sell and a close under the 20-EMA on ${shortDate(e.signal_date)}",
                detail = if (stop) "The stop sits 2 ATR below the entry and trails up with the position" else "Sold at the ${shortDate(e.exit_date)} open",
                tail = ended(e.entry_date, e.entry_price, e.exit_price, e.pnl_pct), tailTone = e.pnl_pct,
                sinceRef = since(e.exit_price, src.ltp),
            )
        }
        sig?.swing?.pending_sell?.let { ps ->
            out += CallRow(
                key = "${src.code}-swing-pending", src = src, kind = Kind.Swing, date = ps.signal_date, waiting = true,
                live = sessionOpen && ps.signal_date == sig.live_date,
                price = ps.signal_close, priceNote = "indicative",
                why = "UT Bot sell and a close under the 20-EMA on the ${shortDate(ps.signal_date)} close",
                detail = "Sells at the next open",
                tail = if (ps.entry_date != null) "Bought ${shortDate(ps.entry_date)} at ${fmt.price(ps.entry_price)}" else "",
                sinceRef = since(ps.signal_close, src.ltp),
            )
        }
        sig?.ath?.exits?.forEachIndexed { i, e ->
            if (e.exit_date !in sessions) return@forEachIndexed
            out += CallRow(
                key = "${src.code}-ath-exit-$i", src = src, kind = Kind.Ath, date = e.exit_date, waiting = false,
                live = sessionOpen && e.exit_date == sig.live_date,
                price = e.exit_price, priceNote = "at the close",
                why = "Closed ${fmt.price(e.exit_price)}, under the 200-DMA",
                detail = "The breakout position is held until a close below the 200-DMA",
                tail = ended(e.entry_date, e.entry_price, e.exit_price, e.pnl_pct), tailTone = e.pnl_pct,
                sinceRef = since(e.exit_price, src.ltp),
            )
        }
    }
    return out.sortedWith(compareByDescending<CallRow> { it.date }.thenBy { it.src.name })
}

/** A segmented control: the web app's `.seg` row of buttons, one on. */
@Composable
fun <T> Seg(options: List<Pair<T, String>>, selected: T, modifier: Modifier = Modifier, onSelect: (T) -> Unit) {
    Row(
        modifier
            .clip(RoundedCornerShape(10.dp))
            .background(Wv.c.surface2)
            .padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        options.forEach { (value, label) ->
            val on = value == selected
            Text(
                label,
                style = Wv.small.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal, fontFeatureSettings = "tnum"),
                color = if (on) Wv.c.text else Wv.c.text2,
                maxLines = 1,
                modifier = Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .background(if (on) Wv.c.surface else Color.Transparent)
                    .clickable { onSelect(value) }
                    .padding(horizontal = 10.dp, vertical = 7.dp),
            )
        }
    }
}

/** Adds the calls view to a LazyColumn so long lists scroll smoothly. */
fun LazyListScope.callsView(
    sources: List<CallSource>,
    fmt: PriceFmt,
    sessionOpen: Boolean,
    state: CallsState,
    onStock: ((CallSource) -> Unit)? = null,
) {
    val hasDetail = sources.any { !it.sig?.last_sessions.isNullOrEmpty() }
    if (!hasDetail) {
        item { Note("Call details are not in the saved signals yet. Press Refresh once to load them.") }
        return
    }
    val pool = if (state.mine) sources.filter { it.held } else sources
    val s2 = latestSessions(sources, 2)
    val s7 = latestSessions(sources, 7)
    val buys = buildBuys(pool, if (state.window == 7) s7 else s2, state.window, fmt, sessionOpen)
    val sells = buildSells(pool, s7, fmt, sessionOpen)
    val counts = mapOf(
        2 to buildBuys(pool, s2, 2, fmt, sessionOpen).count { !it.waiting },
        7 to buildBuys(pool, s7, 7, fmt, sessionOpen).count { !it.waiting },
        OPEN_WINDOW to buildBuys(pool, s2, OPEN_WINDOW, fmt, sessionOpen).count { !it.waiting },
    )
    val rows = if (state.side == "buy") buys else sells
    val filled = rows.filter { !it.waiting }
    val waiting = rows.filter { it.waiting }

    item {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Seg(listOf("buy" to "Buy calls  ${counts[state.window]}", "sell" to "Sell calls  ${sells.count { !it.waiting }}"), state.side) { state.side = it }
            if (state.side == "buy") {
                Seg(
                    listOf(2 to "Last 2 sessions  ${counts[2]}", 7 to "Last 7  ${counts[7]}", OPEN_WINDOW to "All open  ${counts[OPEN_WINDOW]}"),
                    state.window,
                    Modifier.horizontalScroll(rememberScrollState()),
                ) { state.window = it }
            }
            if (sources.any { it.held }) {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { state.mine = !state.mine }) {
                    Checkbox(state.mine, { state.mine = it }, colors = CheckboxDefaults.colors(checkedColor = Wv.c.accent, uncheckedColor = Wv.c.text3))
                    Text("Only my holdings", style = Wv.sub, color = Wv.c.text2)
                }
            }
            val windowLabel = if (state.window == OPEN_WINDOW) "Every position that is open now" else "Buys filled in the last ${state.window} sessions (${s7.takeLast(state.window).joinToString(", ") { weekdayDate(it) }})"
            Text(
                if (state.side == "buy") "$windowLabel. Signals use today's live price as the latest bar." +
                    (if (rows.any { it.live }) " Calls tagged Live fired in the session that is still open and can change before the 15:30 close." else "")
                else "Positions the strategies closed in the last 7 sessions (${s7.joinToString(", ") { weekdayDate(it) }}).",
                style = Wv.small, color = Wv.c.text3,
            )
        }
    }
    listOf(Kind.Swing, Kind.Ath).forEach { kind ->
        val list = filled.filter { it.kind == kind }
        callSection(
            key = "${state.side}-$kind-${state.window}", title = kind.title, sub = kind.sub, accent = { if (kind == Kind.Swing) Wv.c.accent else Wv.c.gain },
            rows = list, side = state.side, fmt = fmt, state = state, onStock = onStock,
            empty = if (state.side == "buy") (if (state.window == OPEN_WINDOW) "No open positions." else "No buys filled in this period.") else "No sells in the last 7 sessions.",
        )
    }
    if (waiting.isNotEmpty()) {
        callSection(
            key = "${state.side}-waiting",
            title = if (state.side == "buy") "Swing buys waiting to fill" else "Swing sells waiting to fill",
            sub = "The latest session's Swing ${state.side} signals. The strategy trades at the next open, so none has filled yet; the price shown is the signal close and the real fill can differ.",
            accent = { Wv.c.warn }, rows = waiting, side = state.side, fmt = fmt, state = state, onStock = onStock, empty = "Nothing is waiting to fill.",
        )
    }
}

/** What the calls view remembers while the screen is open. */
class CallsState(side: String = "buy", window: BuyWindow = 2) {
    var side by mutableStateOf(side)
    var window by mutableIntStateOf(window)
    var mine by mutableStateOf(false)
    val open = androidx.compose.runtime.mutableStateMapOf<String, Boolean>()
    val shown = androidx.compose.runtime.mutableStateMapOf<String, Int>()
}

@Composable
fun rememberCallsState(defaultWindow: BuyWindow = 2) = remember { CallsState(window = defaultWindow) }

private const val CALL_PAGE = 40

private fun LazyListScope.callSection(
    key: String,
    title: String,
    sub: String,
    accent: @Composable () -> Color,
    rows: List<CallRow>,
    side: String,
    fmt: PriceFmt,
    state: CallsState,
    empty: String,
    onStock: ((CallSource) -> Unit)?,
) {
    val open = state.open[key] ?: false
    item(key = "h-$key") {
        WvCard(padding = 14) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { state.open[key] = !open }) {
                Box(Modifier.width(4.dp).height(36.dp).clip(RoundedCornerShape(2.dp)).background(accent()))
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(title, style = Wv.title, color = Wv.c.text)
                    Text(sub, style = Wv.small, color = Wv.c.text3)
                }
                Text("${rows.size}", style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text, modifier = Modifier.padding(horizontal = 8.dp))
                Icon(if (open) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore, contentDescription = if (open) "Hide" else "Show", tint = Wv.c.text3)
            }
            if (open && rows.isEmpty()) Text(empty, style = Wv.sub, color = Wv.c.text3)
        }
    }
    if (!open || rows.isEmpty()) return
    val shown = state.shown[key] ?: CALL_PAGE
    val grouped = if (rows.all { it.waiting }) listOf("" to rows) else rows.groupBy { it.date }.toSortedMap(reverseOrder()).map { (d, r) -> "${if (side == "buy") "Entered" else "Exited"} ${weekdayDate(d)}" to r }
    var budget = shown
    grouped.forEach { (groupTitle, groupRows) ->
        if (budget <= 0) return@forEach
        val take = groupRows.take(budget)
        budget -= take.size
        if (groupTitle.isNotEmpty()) {
            item(key = "g-$key-$groupTitle") {
                Row(Modifier.padding(start = 4.dp, top = 4.dp)) {
                    Text(groupTitle.uppercase(), style = Wv.over, color = Wv.c.text3, modifier = Modifier.weight(1f))
                    Text("${groupRows.size}", style = Wv.over, color = Wv.c.text3)
                }
            }
        }
        take.forEach { c -> item(key = "r-$key-${c.key}") { CallCard(c, side, fmt, onStock) } }
    }
    if (rows.size > shown) {
        item(key = "m-$key") {
            OutlinedButton(onClick = { state.shown[key] = shown + CALL_PAGE }, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Text("Show ${minOf(CALL_PAGE, rows.size - shown)} more of ${rows.size - shown}", color = Wv.c.text)
            }
        }
    }
}

@Composable
private fun CallCard(c: CallRow, side: String, fmt: PriceFmt, onStock: ((CallSource) -> Unit)?) {
    WvCard(padding = 14, modifier = Modifier.animateContentSize().then(if (onStock != null) Modifier.clickable { onStock(c.src) } else Modifier)) {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(c.src.name, style = Wv.title, color = Wv.c.text, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    if (c.src.isNew) Badge("New", Tone.Info)
                    if (c.src.held) Badge("Held", Tone.Ok)
                    if (c.live) Badge("Live", Tone.Warn)
                }
                Text(c.src.code + (c.src.sector?.let { " · $it" } ?: ""), style = Wv.small, color = Wv.c.text3, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(fmt.price(c.price), style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                Text(if (c.waiting) "${weekdayDate(c.date)} · ${c.priceNote}" else "${shortDate(c.date)} · ${c.priceNote}", style = Wv.small, color = Wv.c.text3)
            }
        }
        Text(c.why, style = Wv.sub, color = Wv.c.text)
        Text(c.detail, style = Wv.small, color = Wv.c.text3)
        HorizontalDivider(color = Wv.c.border)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(c.tail.ifBlank { "—" }, style = Wv.small, color = if (c.tailTone != null) toneOf(c.tailTone) else Wv.c.text2, modifier = Modifier.weight(1f))
            Column(horizontalAlignment = Alignment.End) {
                Text("Now ${fmt.price(c.src.ltp)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text2)
                c.sinceRef?.let {
                    Text("${pct(it.pct)} since ${if (side == "buy") "entry" else "exit"}", style = Wv.small.copy(fontFeatureSettings = "tnum", fontWeight = FontWeight.SemiBold), color = toneOf(it.abs))
                }
            }
        }
    }
}

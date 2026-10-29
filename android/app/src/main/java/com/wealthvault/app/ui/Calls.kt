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

/** Today's date when the signals were rebuilt on a live price (today's bar is still forming), else null. */
fun liveSessionDate(sources: List<CallSource>): String? = sources.mapNotNull { it.sig?.live_date }.maxOrNull()

/**
 * The window for "last `n` sessions": the `n` most recent FINISHED sessions seen across all stocks (each stock
 * reports its own), plus today when live prices are in. Today never pushes a finished session out of the window.
 */
fun latestSessions(sources: List<CallSource>, n: Int): List<String> {
    val live = sources.mapNotNull { it.sig?.live_date }.toSet()
    val finished = sources.flatMap { it.sig?.last_sessions.orEmpty() }.filter { it !in live }.toSortedSet().toList().takeLast(n)
    val last = finished.lastOrNull().orEmpty()
    return finished + live.filter { it > last }.sorted()
}

fun buildBuys(sources: List<CallSource>, sessions: List<String>, window: BuyWindow, fmt: PriceFmt, sessionOpen: Boolean): List<CallRow> {
    val out = mutableListOf<CallRow>()
    val inWindow = { d: String? -> d != null && (window == OPEN_WINDOW || d in sessions) }
    sources.forEach { src ->
        val sig = src.sig
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

/** Window OPEN_WINDOW means every closed trade on record (the latest few per stock and strategy), however long ago. */
fun buildSells(sources: List<CallSource>, sessions: List<String>, fmt: PriceFmt, sessionOpen: Boolean, window: BuyWindow = 7): List<CallRow> {
    val out = mutableListOf<CallRow>()
    val inWindow = { d: String -> window == OPEN_WINDOW || d in sessions }
    val ended = { entryDate: String, entryPrice: Double?, exitPrice: Double?, pnl: Double? ->
        "Bought ${shortDate(entryDate)} at ${fmt.price(entryPrice)}, sold ${fmt.price(exitPrice)}" + (pnl?.let { " (${signed1(it)})" } ?: "")
    }
    sources.forEach { src ->
        val sig = src.sig
        sig?.ath?.exits?.forEachIndexed { i, e ->
            if (!inWindow(e.exit_date)) return@forEachIndexed
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
                    // a little taller than the text: easier to hit with a thumb
                    .padding(horizontal = 12.dp, vertical = 9.dp),
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
    val today = liveSessionDate(sources)
    val inWindow = if (state.window == 7) s7 else s2
    val buys = buildBuys(pool, inWindow, state.window, fmt, sessionOpen)
    val sells = buildSells(pool, inWindow, fmt, sessionOpen, state.window)
    val sellCounts = mapOf(
        2 to buildSells(pool, s2, fmt, sessionOpen, 2).count { !it.waiting },
        7 to buildSells(pool, s7, fmt, sessionOpen, 7).count { !it.waiting },
        OPEN_WINDOW to buildSells(pool, s2, fmt, sessionOpen, OPEN_WINDOW).count { !it.waiting },
    )
    val counts = mapOf(
        2 to buildBuys(pool, s2, 2, fmt, sessionOpen).count { !it.waiting },
        7 to buildBuys(pool, s7, 7, fmt, sessionOpen).count { !it.waiting },
        OPEN_WINDOW to buildBuys(pool, s2, OPEN_WINDOW, fmt, sessionOpen).count { !it.waiting },
    )
    val rows = if (state.side == "buy") buys else sells
    val filled = rows.filter { !it.waiting }
    val waiting = rows.filter { it.waiting }

    item {
        // stacked toggles get room between them, so a tap cannot land on the row above or below
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Seg(listOf("buy" to "Buy calls  ${counts[state.window]}", "sell" to "Sell calls  ${sellCounts[state.window]}"), state.side) { state.side = it }
            val shownCounts = if (state.side == "buy") counts else sellCounts
            Seg(
                listOf(2 to "Last 2 sessions  ${shownCounts[2]}", 7 to "Last 7  ${shownCounts[7]}", OPEN_WINDOW to "${if (state.side == "buy") "All open" else "All recorded"}  ${shownCounts[OPEN_WINDOW]}"),
                state.window,
                Modifier.horizontalScroll(rememberScrollState()),
            ) { state.window = it }
            if (sources.any { it.held }) {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { state.mine = !state.mine }) {
                    Checkbox(state.mine, { state.mine = it }, colors = CheckboxDefaults.colors(checkedColor = Wv.c.accent, uncheckedColor = Wv.c.text3))
                    Text("Only my holdings", style = Wv.sub, color = Wv.c.text2)
                }
            }
            val todayNote = if (today != null && today in inWindow) " plus today, live (${weekdayDate(today)})" else ""
            val windowLabel = if (state.window == OPEN_WINDOW) "Every position that is open now" else "Buys filled in the last ${state.window} sessions$todayNote (${inWindow.joinToString(", ") { weekdayDate(it) }})"
            Text(
                if (state.side == "buy") "$windowLabel. Signals use today's live price as the latest bar." +
                    (if (rows.any { it.live }) " Calls tagged Live fired in the session that is still open and can change before the 15:30 close." else "")
                else if (state.window == OPEN_WINDOW) "Every closed trade on record: the latest few per stock and strategy, however long ago."
                else "Positions the strategies closed in the last ${state.window} sessions$todayNote (${inWindow.joinToString(", ") { weekdayDate(it) }}).",
                style = Wv.small, color = Wv.c.text3,
            )
        }
    }
    listOf(Kind.Ath).forEach { kind ->
        val list = filled.filter { it.kind == kind }
        callSection(
            key = "${state.side}-$kind-${state.window}", title = kind.title, sub = kind.sub, accent = { Wv.c.gain },
            rows = list, side = state.side, fmt = fmt, state = state, onStock = onStock,
            empty = if (state.side == "buy") (if (state.window == OPEN_WINDOW) "No open positions." else "No buys filled in this period.") else if (state.window == OPEN_WINDOW) "No closed trades on record." else "No sells in this period.",
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

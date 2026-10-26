package com.wealthvault.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Cancel
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import kotlinx.coroutines.delay
import com.wealthvault.app.data.StockSuggestion
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import com.wealthvault.app.data.MomentumAnalysis
import com.wealthvault.app.data.StrategyResult
import com.wealthvault.app.data.StrategyTrade
import com.wealthvault.app.data.TrendCheck

/** The stocks you hold most of, as exchange ids where the signals know them (INDmoney's own codes mean nothing to Kite). */
@Composable
fun quickPicks(vm: AppViewModel, avm: AnalysisViewModel): List<Pair<String, String>> {
    val holdings by vm.holdings.collectAsState()
    val signals by avm.signals.collectAsState()
    val map = signals.data?.symbol_map.orEmpty()
    return remember(holdings.data, map) {
        holdings.data.orEmpty().filter { it.asset_class == "EQUITY" }.sortedByDescending { it.current_value }
            .mapNotNull { h ->
                val id = map[h.instrument_symbol] ?: tickerOf(h.instrument_symbol).takeIf { !it.startsWith("INDS") } ?: return@mapNotNull null
                id to id.substringAfter(':')
            }
            .distinctBy { it.first }
            .take(12)
    }
}

@Composable
private fun SymbolPicker(
    initial: String,
    picks: List<Pair<String, String>>,
    busy: Boolean,
    action: String,
    suggest: suspend (String) -> List<StockSuggestion>,
    onRun: (String) -> Unit,
) {
    var text by rememberSaveable(initial) { mutableStateOf(initial.substringAfter(':')) }
    // suggestions come from the third typed character; a value filled in by a pick or a link asks for none
    var typed by remember { mutableStateOf(false) }
    var suggestions by remember { mutableStateOf<List<StockSuggestion>>(emptyList()) }
    var searched by remember { mutableStateOf(false) }
    LaunchedEffect(text, typed) {
        val q = text.trim()
        if (!typed || q.length < 3 || ':' in q) { suggestions = emptyList(); searched = false; return@LaunchedEffect }
        delay(250)
        suggestions = suggest(q)
        searched = true
    }
    val focus = LocalFocusManager.current
    val go = { v: String -> if (v.isNotBlank()) { typed = false; suggestions = emptyList(); focus.clearFocus(); onRun(v) } }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                text, { text = it.uppercase(); typed = true },
                placeholder = { Text("Name or symbol, e.g. reli or INFY") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, imeAction = ImeAction.Go),
                keyboardActions = KeyboardActions(onGo = { go(text) }),
                modifier = Modifier.weight(1f),
            )
            PrimaryButton(if (busy) "…" else action, busy = busy, enabled = text.isNotBlank()) { go(text) }
        }
        if (searched && suggestions.isEmpty()) {
            Text("No stock matches that, or suggestions are unavailable. Type the full symbol instead.", style = Wv.small, color = Wv.c.text3)
        }
        if (suggestions.isNotEmpty()) {
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Wv.c.surface)) {
                suggestions.forEach { s ->
                    Row(
                        Modifier.fillMaxWidth().clickable { text = s.symbol.substringAfter(':'); go(s.symbol) }.padding(horizontal = 14.dp, vertical = 12.dp),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(s.symbol, style = Wv.body.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text, maxLines = 1)
                        Text(s.name, style = Wv.small, color = Wv.c.text3, maxLines = 1, modifier = Modifier.weight(1f))
                    }
                    HorizontalDivider(color = Wv.c.border)
                }
            }
        }
        if (picks.isNotEmpty()) {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("YOUR HOLDINGS", style = Wv.over, color = Wv.c.text3)
                picks.forEach { (id, label) -> Chip(label, false) { text = label; go(id) } }
            }
        }
    }
}

@Composable
private fun Checks(checks: List<TrendCheck>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        checks.forEach { c ->
            Row(verticalAlignment = Alignment.Top) {
                Icon(
                    if (c.passed) Icons.Outlined.CheckCircle else Icons.Outlined.Cancel,
                    contentDescription = if (c.passed) "Passed" else "Failed",
                    tint = if (c.passed) Wv.c.gain else Wv.c.loss,
                    modifier = Modifier.padding(top = 1.dp).width(18.dp),
                )
                Spacer(Modifier.width(8.dp))
                Column {
                    Text(c.label, style = Wv.body, color = Wv.c.text)
                    if (c.detail.isNotBlank()) Text(c.detail, style = Wv.small, color = Wv.c.text3)
                }
            }
        }
    }
}

/** A label and a value on one line. */
@Composable
fun StatLine(label: String, value: String, valueTone: androidx.compose.ui.graphics.Color? = null, note: String? = null) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 2.dp)) {
        Text(label, style = Wv.sub, color = Wv.c.text2, modifier = Modifier.weight(1f))
        Column(horizontalAlignment = Alignment.End) {
            Text(value, style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = valueTone ?: Wv.c.text)
            if (note != null) Text(note, style = Wv.small, color = Wv.c.text3)
        }
    }
}

@Composable
private fun Loading(text: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(vertical = 8.dp)) {
        CircularProgressIndicator(Modifier.width(18.dp).height(18.dp), color = Wv.c.accent, strokeWidth = 2.dp)
        Text(text, style = Wv.sub, color = Wv.c.text2)
    }
}

// --- momentum ------------------------------------------------------------------------------------------------

@Composable
fun MomentumScreen(vm: AppViewModel, avm: AnalysisViewModel, request: AnalysisViewModel.StockRequest?, onStrategies: (String) -> Unit) {
    val res by avm.momentum.collectAsState()
    val picks = quickPicks(vm, avm)
    val symbol = request?.takeIf { it.kind == "momentum" }?.symbol
    LaunchedEffect(request?.id) {
        avm.takeStockRequest("momentum")?.let { r ->
            if (avm.momentum.value.data?.instrument?.endsWith(r.symbol.substringAfter(':')) != true) avm.analyse(r.symbol)
        }
    }
    LaunchedEffect(Unit) { if (avm.signals.value.data == null) avm.loadSignals() }
    val m = res.data

    LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            PageTitle(
                "Momentum",
                "Trend verdict from moving averages (50/200-DMA, golden cross, 200-DMA slope, MACD), plus returns, RSI, 52-week range and strength vs the Nifty 50. One year of daily prices from Zerodha Kite.",
            )
        }
        item { SymbolPicker(symbol ?: m?.instrument ?: "", picks, res.loading, "Analyse", avm::suggest) { avm.analyse(it) } }
        res.problem?.let { item { ProblemNote(it) } }
        if (res.loading) item { Loading("Fetching one year of daily prices…") }
        if (m != null && !res.loading) momentumBody(m, onStrategies)
        if (m == null && !res.loading && res.problem == null) item { Note("Pick one of your holdings or type a symbol. NSE symbols work directly (INFY); use BSE:CODE for BSE-only stocks.") }
    }
}

/** A 0-100 scale with a dot where the value sits, and quiet ticks (RSI, the 52-week range). */
@Composable
private fun ScaleBar(fraction: Double, marks: List<Double> = emptyList(), band: ClosedFloatingPointRange<Double>? = null) {
    val ink = Wv.c.text
    val track = Wv.c.surface2
    val mid = Wv.c.border
    val ring = Wv.c.surface
    androidx.compose.foundation.Canvas(Modifier.fillMaxWidth().height(14.dp)) {
        val w = size.width
        val cy = size.height / 2
        drawRoundRect(track, topLeft = androidx.compose.ui.geometry.Offset(0f, cy - 4.dp.toPx()), size = androidx.compose.ui.geometry.Size(w, 8.dp.toPx()), cornerRadius = androidx.compose.ui.geometry.CornerRadius(4.dp.toPx()))
        band?.let { b -> drawRect(mid, topLeft = androidx.compose.ui.geometry.Offset((w * b.start).toFloat(), cy - 4.dp.toPx()), size = androidx.compose.ui.geometry.Size((w * (b.endInclusive - b.start)).toFloat(), 8.dp.toPx())) }
        marks.forEach { f -> drawLine(mid, androidx.compose.ui.geometry.Offset((w * f).toFloat(), cy - 6.dp.toPx()), androidx.compose.ui.geometry.Offset((w * f).toFloat(), cy + 6.dp.toPx()), strokeWidth = 1.dp.toPx()) }
        val x = (w * fraction.coerceIn(0.0, 1.0)).toFloat()
        drawCircle(ring, radius = 7.dp.toPx(), center = androidx.compose.ui.geometry.Offset(x, cy))
        drawCircle(ink, radius = 5.dp.toPx(), center = androidx.compose.ui.geometry.Offset(x, cy))
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.momentumBody(m: MomentumAnalysis, onStrategies: (String) -> Unit) {
    item {
        WvCard {
            Text("${m.instrument} · as of ${longDate(m.as_of)}${if (m.live_bar) " (live price)" else ""} · ${m.candles_used} trading days", style = Wv.small, color = Wv.c.text3)
            Text(m.name ?: m.instrument, style = Wv.title, color = Wv.c.text)
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(price(m.last_price), style = Wv.kpi.copy(fontSize = Wv.title.fontSize * 1.5f), color = Wv.c.text)
                m.returns["1M"]?.let { r -> Text("${pct(r)} 1M", style = Wv.sub.copy(fontFeatureSettings = "tnum", fontWeight = FontWeight.SemiBold), color = toneOf(r)) }
            }
            Text("TREND VERDICT (MOVING AVERAGES)", style = Wv.over, color = Wv.c.text3)
            val ratio = if (m.trend_max_score > 0) m.trend_score * 5.0 / m.trend_max_score else 0.0
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Badge(m.trend_verdict, if (ratio >= 3.5) Tone.Ok else if (ratio <= 1.5) Tone.Bad else Tone.Warn)
                // one pip per rule, filled for each point scored
                Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                    m.trend_checks.forEachIndexed { i, _ ->
                        Box(Modifier.width(18.dp).height(6.dp).clip(RoundedCornerShape(3.dp)).background(if (i < m.trend_score) Wv.c.gain else Wv.c.border))
                    }
                }
                Text("${m.trend_score}/${m.trend_max_score}", style = Wv.small.copy(fontFeatureSettings = "tnum", fontWeight = FontWeight.SemiBold), color = Wv.c.text2)
            }
            OutlinedButton(onClick = { onStrategies(m.instrument) }, shape = RoundedCornerShape(10.dp)) { Text("Run Swing V2.1 strategy", color = Wv.c.accent) }
        }
    }
    item {
        WvCard {
            Label("Trend checklist")
            Text("Each rule that holds adds one point", style = Wv.small, color = Wv.c.text3)
            Checks(m.trend_checks)
            if (m.trend_max_score < 5) Note("Some rules need more price history (200-DMA needs 200 trading days) and were skipped.")
        }
    }
    if (m.series.size > 1) {
        item {
            WvCard {
                Label("Price vs moving averages · 1Y")
                LineChart(
                    m.series.map { it.date },
                    listOf(
                        Series("Close", Wv.c.accent, m.series.map { it.close }),
                        Series("50-DMA", Wv.c.gain, m.series.map { it.sma50 }, dashed = true),
                        Series("200-DMA", Wv.c.warn, m.series.map { it.sma200 }),
                    ),
                    format = { price(it) },
                )
            }
        }
    }
    item {
        WvCard {
            Label("Price momentum")
            Text("Return, and vs ${m.benchmark.ifBlank { "the index" }} (percentage points)", style = Wv.small, color = Wv.c.text3)
            Row {
                Text("Window", style = Wv.small, color = Wv.c.text3, modifier = Modifier.weight(1f))
                Text("Return", style = Wv.small, color = Wv.c.text3, modifier = Modifier.width(80.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
                Text("vs index", style = Wv.small, color = Wv.c.text3, modifier = Modifier.width(96.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
            }
            listOf("1M", "3M", "6M", "12M", "12-1").forEach { w ->
                val r = m.returns[w]
                val rs = m.relative_strength[w]
                Row(Modifier.padding(vertical = 2.dp)) {
                    Text(if (w == "12-1") "12M excl. last 1M" else w, style = Wv.sub, color = Wv.c.text2, modifier = Modifier.weight(1f))
                    Text(pct(r), style = Wv.num, color = toneOf(r), modifier = Modifier.width(80.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
                    Text(if (w == "12-1") "" else pct(rs), style = Wv.num, color = toneOf(rs), modifier = Modifier.width(96.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
                }
            }
        }
    }
    item {
        WvCard {
            Label("Risk-adjusted")
            Text("Return ÷ annualised volatility", style = Wv.small, color = Wv.c.text3)
            StatLine("6M score", m.risk_adjusted_6m?.let { String.format("%.2f", it).replace("-", "−") } ?: "—", toneOf(m.risk_adjusted_6m))
            StatLine("12M score", m.risk_adjusted_12m?.let { String.format("%.2f", it).replace("-", "−") } ?: "—", toneOf(m.risk_adjusted_12m))
            StatLine("6M volatility", m.volatility_6m?.let { String.format("%.1f%%", it) } ?: "—")
            StatLine("12M volatility", m.volatility_12m?.let { String.format("%.1f%%", it) } ?: "—")
            Text("Above 1 means the return outweighed the volatility taken to get it.", style = Wv.small, color = Wv.c.text3)
        }
    }
    item {
        WvCard {
            Label("RSI (14)")
            Text("Short-term strength oscillator", style = Wv.small, color = Wv.c.text3)
            val rsi = m.rsi_14
            if (rsi == null) {
                Text("Not enough data", style = Wv.sub, color = Wv.c.text3)
            } else {
                val (zone, tone) = when {
                    rsi >= 70 -> "Overbought" to Wv.c.warn
                    rsi >= 50 -> "Bullish" to Wv.c.gain
                    rsi > 30 -> "Bearish" to Wv.c.loss
                    else -> "Oversold" to Wv.c.warn
                }
                Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(String.format("%.1f", rsi), style = Wv.kpi, color = Wv.c.text)
                    Text(zone, style = Wv.sub.copy(fontWeight = FontWeight.SemiBold), color = tone)
                }
                ScaleBar(rsi / 100, marks = listOf(0.3, 0.5, 0.7), band = 0.3..0.7)
                Row {
                    listOf("0", "30", "50", "70", "100").forEachIndexed { i, t ->
                        Text(t, style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3, modifier = Modifier.weight(1f), textAlign = when (i) { 0 -> androidx.compose.ui.text.style.TextAlign.Start; 4 -> androidx.compose.ui.text.style.TextAlign.End; else -> androidx.compose.ui.text.style.TextAlign.Center })
                    }
                }
            }
        }
    }
    item {
        WvCard {
            Label("52-week range")
            Text("Where the price sits in its one-year range", style = Wv.small, color = Wv.c.text3)
            val hi = m.high_52w
            val lo = m.low_52w
            if (hi != null && lo != null && hi > lo) {
                ScaleBar((m.last_price - lo) / (hi - lo))
                Row {
                    Text(price(lo), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3, modifier = Modifier.weight(1f))
                    Text(price(hi), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
                }
            }
            StatLine("From 52W high", pct(m.pct_from_52w_high), toneOf(m.pct_from_52w_high))
            StatLine("From 52W low", pct(m.pct_from_52w_low), toneOf(m.pct_from_52w_low))
        }
    }
    item {
        WvCard {
            Label("Moving averages and MACD")
            StatLine("20-DMA", price(m.sma_20))
            StatLine("50-DMA", price(m.sma_50), note = m.pct_from_sma50?.let { "price ${pct(it)}" })
            StatLine("200-DMA", price(m.sma_200), note = m.pct_from_sma200?.let { "price ${pct(it)}" })
            StatLine("200-DMA slope (20d)", pct(m.sma200_slope_pct), toneOf(m.sma200_slope_pct))
            StatLine(
                "50/200 cross",
                m.cross_state?.let { (if (it == "golden") "Golden" else "Death") + (m.days_since_cross?.let { d -> " · ${d}d ago" } ?: "") } ?: "—",
                when (m.cross_state) { "golden" -> Wv.c.gain; "death" -> Wv.c.loss; else -> Wv.c.text3 },
            )
            StatLine("MACD (12, 26)", m.macd?.let { String.format("%.2f", it).replace("-", "−") } ?: "—")
            StatLine("Signal (9)", m.macd_signal?.let { String.format("%.2f", it).replace("-", "−") } ?: "—")
            StatLine("Histogram", m.macd_histogram?.let { String.format("%.2f", it).replace("-", "−") } ?: "—", toneOf(m.macd_histogram))
        }
    }
    item { Text("Momentum describes past price behaviour; it is not a forecast or investment advice. Trend signals lag and can reverse sharply around market turning points.", style = Wv.small, color = Wv.c.text3) }
}

/** The strategies' exit codes in words. */
private fun exitReason(code: String) = when (code) {
    "ATR STOP" -> "stop hit"
    "UT + EMA20 SELL" -> "sell signal"
    "200DMA BREAK" -> "closed under the DMA"
    else -> code.lowercase()
}

// --- strategies ----------------------------------------------------------------------------------------------

@Composable
private fun NumberField(label: String, value: String, modifier: Modifier = Modifier, onChange: (String) -> Unit) {
    OutlinedTextField(
        value, { v -> onChange(v.filter { it.isDigit() || it == '.' }.take(8)) },
        label = { Text(label) }, singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Decimal),
        modifier = modifier,
    )
}

/** The inputs a strategy run takes, as on the web; the rest of each script's settings are fixed. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun StrategyInputs(avm: AnalysisViewModel, ath: Boolean, busy: Boolean, canRun: Boolean, onApply: () -> Unit) {
    var open by rememberSaveable { mutableStateOf(false) }
    val swing by avm.swingOpts.collectAsState()
    val athO by avm.athOpts.collectAsState()
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { open = !open }) {
            Text("INPUTS", style = Wv.over, color = Wv.c.text3, modifier = Modifier.weight(1f))
            Text(
                if (ath) "From ${athO.startDate} · ${athO.dmaLength}-DMA · ${athO.windowBars}-day window · ${compact(athO.capital)} a trade"
                else "${swing.years}Y · UT key ${swing.utKey} · ATR ${swing.utAtrPeriod} · stop ${if (swing.useStop) "${swing.stopMult}×ATR" else "off"}",
                style = Wv.small, color = Wv.c.text2, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, modifier = Modifier.weight(2f),
            )
            Icon(if (open) androidx.compose.material.icons.Icons.Outlined.ExpandLess else androidx.compose.material.icons.Icons.Outlined.ExpandMore, contentDescription = if (open) "Hide inputs" else "Show inputs", tint = Wv.c.text3)
        }
        if (!open) return@WvCard
        if (!ath) {
            Text("Backtest", style = Wv.small, color = Wv.c.text3)
            Seg(listOf(1, 2, 3, 5).map { it to "${it}Y" }, swing.years) { avm.swingOpts.value = swing.copy(years = it) }
            androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                var utKey by remember { mutableStateOf(swing.utKey.toString()) }
                var atr by remember { mutableStateOf(swing.utAtrPeriod.toString()) }
                var mult by remember { mutableStateOf(swing.stopMult.toString()) }
                NumberField("UT key", utKey, Modifier.width(110.dp)) { utKey = it; it.toDoubleOrNull()?.let { v -> avm.swingOpts.value = avm.swingOpts.value.copy(utKey = v) } }
                NumberField("UT ATR period", atr, Modifier.width(130.dp)) { atr = it; it.toDoubleOrNull()?.let { v -> avm.swingOpts.value = avm.swingOpts.value.copy(utAtrPeriod = v.toInt().coerceAtLeast(1)) } }
                NumberField("Stop ATR ×", mult, Modifier.width(110.dp)) { mult = it; it.toDoubleOrNull()?.let { v -> avm.swingOpts.value = avm.swingOpts.value.copy(stopMult = v) } }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                androidx.compose.material3.Switch(
                    swing.useStop, { avm.swingOpts.value = swing.copy(useStop = it) },
                    colors = androidx.compose.material3.SwitchDefaults.colors(checkedTrackColor = Wv.c.accent, checkedThumbColor = Wv.c.onAccent, uncheckedTrackColor = Wv.c.surface2, uncheckedThumbColor = Wv.c.text3, uncheckedBorderColor = Wv.c.borderStrong),
                )
                Spacer(Modifier.width(8.dp))
                Text("ATR protective stop", style = Wv.sub, color = Wv.c.text2)
            }
            Text("Fixed: 50/200-SMA · 20-bar slope · 20-EMA exit · ATR(14) stop · ₹1,00,000 · 0.10% commission · 1 tick slippage", style = Wv.small, color = Wv.c.text3)
        } else {
            androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                var start by remember { mutableStateOf(athO.startDate) }
                var dma by remember { mutableStateOf(athO.dmaLength.toString()) }
                var window by remember { mutableStateOf(athO.windowBars.toString()) }
                var capital by remember { mutableStateOf(athO.capital.toLong().toString()) }
                OutlinedTextField(
                    start, { v -> start = v.filter { it.isDigit() || it == '-' }.take(10); if (Regex("""\d{4}-\d{2}-\d{2}""").matches(start)) avm.athOpts.value = avm.athOpts.value.copy(startDate = start) },
                    label = { Text("Backtest start") }, placeholder = { Text("2015-01-01") }, singleLine = true, modifier = Modifier.width(150.dp),
                )
                NumberField("DMA length", dma, Modifier.width(120.dp)) { dma = it; it.toDoubleOrNull()?.let { v -> avm.athOpts.value = avm.athOpts.value.copy(dmaLength = v.toInt().coerceIn(50, 400)) } }
                NumberField("Window (days)", window, Modifier.width(130.dp)) { window = it; it.toDoubleOrNull()?.let { v -> avm.athOpts.value = avm.athOpts.value.copy(windowBars = v.toInt().coerceAtLeast(1)) } }
                NumberField("Capital / trade ₹", capital, Modifier.width(150.dp)) { capital = it; it.toDoubleOrNull()?.let { v -> avm.athOpts.value = avm.athOpts.value.copy(capital = v.coerceAtLeast(1000.0)) } }
            }
            Text("Fixed: fills at the signal close · no commission (as in the script) · capital per trade does not compound", style = Wv.small, color = Wv.c.text3)
        }
        PrimaryButton(if (busy) "Running…" else "Apply", busy = busy, enabled = canRun) { onApply() }
    }
}

@Composable
fun StrategyScreen(vm: AppViewModel, avm: AnalysisViewModel, request: AnalysisViewModel.StockRequest?) {
    var tab by rememberSaveable { mutableStateOf("swing") }
    var current by rememberSaveable { mutableStateOf(request?.takeIf { it.kind == "strategy" }?.symbol.orEmpty()) }
    val swing by avm.swing.collectAsState()
    val ath by avm.ath.collectAsState()
    val res = if (tab == "ath") ath else swing
    val picks = quickPicks(vm, avm)
    LaunchedEffect(request?.id) {
        avm.takeStockRequest("strategy")?.let { r -> current = r.symbol; avm.runStrategy("swing", r.symbol); avm.runStrategy("ath", r.symbol) }
    }
    LaunchedEffect(Unit) { if (avm.signals.value.data == null) avm.loadSignals() }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { PageTitle("Strategies", "Run a strategy on any NSE/BSE stock: today's signal, the chart with entries and exits, and a backtest of every past trade. Prices from Zerodha Kite.") }
        item {
            Seg(listOf("swing" to "Swing V2.1", "ath" to "200-DMA ATH breakout"), tab) { t ->
                tab = t
                val r = if (t == "ath") avm.ath.value else avm.swing.value
                if (current.isNotBlank() && r.data == null && !r.loading) avm.runStrategy(t, current)
            }
        }
        item {
            Text(
                if (tab == "ath") "Buys when the close breaks above the prior all-time high within the window after a close below the DMA, and holds until a close below the DMA. Orders fill at the signal day's close, with a fixed amount per trade."
                else "Long-only daily swing strategy. Buys a UT Bot cross-up while the 50/200-SMA trend filter is bullish; exits on a UT Bot flip with a close under the 20-EMA, or at the ATR protective stop. Orders fill at the next open.",
                style = Wv.small, color = Wv.c.text3,
            )
        }
        item { SymbolPicker(current, picks, res.loading, "Run", avm::suggest) { current = it; avm.runStrategy(tab, it) } }
        item { StrategyInputs(avm, tab == "ath", res.loading, current.isNotBlank()) { avm.runStrategy(tab, current) } }
        res.problem?.let { item { ProblemNote(it) } }
        if (res.loading) item { Loading(if (tab == "ath") "Fetching the full daily price history and running the backtest…" else "Fetching daily prices and running the backtest…") }
        if (!res.loading) res.data?.let { strategyBody(it, tab == "ath") }
        if (res.data == null && !res.loading && res.problem == null) item { Note("Pick one of your holdings or type a symbol.") }
    }
}

/** A price chart with the strategy's lines, its buys, sells and stop exits, and the days its setup was on. */
@Composable
private fun StrategyPriceChart(r: StrategyResult, ath: Boolean) {
    val ranges = if (ath) listOf(252 to "1Y", 756 to "3Y", 1260 to "5Y", 0 to "All") else listOf(126 to "6M", 252 to "1Y", 504 to "2Y", 0 to "All")
    var range by rememberSaveable(ath) { mutableStateOf(if (ath) 0 else 252) }
    val bars = if (range > 0) r.series.takeLast(range) else r.series
    if (bars.size < 2) return
    val dmaLabel = "${r.params.dma_length ?: 200}-DMA"
    val stopFills = r.trades.filter { it.exit_reason == "ATR STOP" && it.exit_date != null }.associate { it.exit_date!! to it.exit_price }
    val buy = Wv.c.gain
    val sell = Wv.c.loss
    val markers = bars.flatMapIndexed { i, b ->
        listOfNotNull(
            if (b.buy) ChartMarker(i, if (ath) b.close * 0.96 else b.low * 0.975, ChartMarker.Kind.Up, buy) else null,
            if (b.sell) ChartMarker(i, b.high * if (ath) 1.04 else 1.025, ChartMarker.Kind.Down, sell) else null,
            if (b.stop_exit) ChartMarker(i, stopFills[b.date] ?: b.low, ChartMarker.Kind.Cross, sell) else null,
        )
    }
    // runs of days with the setup on (a bullish regime for Swing, the window after a DMA break for ATH)
    val on = bars.map { if (ath) it.in_window else it.regime }
    val bands = mutableListOf<IntRange>()
    var start = -1
    on.forEachIndexed { i, v ->
        if (v && start < 0) start = i
        if ((!v || i == on.lastIndex) && start >= 0) { bands += start..(if (v) i else i - 1); start = -1 }
    }
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(if (ath) "PRICE, DMA, ALL-TIME HIGH AND SIGNALS" else "PRICE, INDICATORS AND SIGNALS", style = Wv.over, color = Wv.c.text3, modifier = Modifier.weight(1f))
        }
        Seg(ranges, range) { range = it }
        LineChart(
            bars.map { it.date },
            if (ath) listOf(
                Series("Close", Wv.c.text, bars.map { it.close }, thin = true),
                Series(dmaLabel, Wv.c.warn, bars.map { it.dma }),
                Series("All-time high", Wv.c.text3, bars.map { it.ath }, dashed = true, step = true, thin = true),
            ) else listOf(
                Series("Close", Wv.c.text, bars.map { it.close }, thin = true),
                Series("50-SMA", Wv.c.accent, bars.map { it.sma_fast }),
                Series("200-SMA", Wv.c.warn, bars.map { it.sma_slow }),
                Series("20-EMA", Wv.c.gain, bars.map { it.exit_ema }, dashed = true, thin = true),
                Series("UT stop", Wv.c.text3, bars.map { it.ut_stop }, dashed = true, step = true, thin = true),
            ),
            format = { price(it) },
            height = 240.dp,
            markers = markers,
            bands = bands,
            bandColor = Wv.c.gain,
            bandLabel = if (ath) "Setup window" else "Bullish regime",
        )
        Text("▲ buy   ▼ sell" + if (!ath) "   ✕ stop exit" else "", style = Wv.small, color = Wv.c.text3)
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.strategyBody(r: StrategyResult, ath: Boolean) {
    val st = r.status
    val s = r.stats
    val dmaLabel = "${r.params.dma_length ?: 200}-DMA"
    item {
        WvCard {
            Text("${r.instrument} · signals as of ${longDate(r.as_of)} close", style = Wv.small, color = Wv.c.text3)
            Text(r.name ?: r.instrument, style = Wv.title, color = Wv.c.text)
            val badge = if (ath) when {
                st.last_signal == "BUY" -> "Bought today" to Tone.Ok
                st.last_signal == "SELL" -> "Sold today" to Tone.Bad
                st.state == "IN_POSITION" -> "In position" to Tone.Info
                st.in_window == true -> "Setup active" to Tone.Warn
                else -> "No setup" to Tone.Off
            } else when {
                st.pending_order == "BUY" -> "BUY signal" to Tone.Ok
                st.pending_order == "SELL" -> "SELL signal" to Tone.Bad
                st.state == "IN_POSITION" -> "In position" to Tone.Info
                st.regime_bullish == true -> "Waiting for entry" to Tone.Warn
                else -> "No trade" to Tone.Off
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Badge(badge.first, badge.second)
                Text(st.headline, style = Wv.sub.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
            }
            if (st.detail.isNotBlank()) Text(st.detail, style = Wv.small, color = Wv.c.text2)
            if (r.live_bar) Note("Today's bar uses the live price (${price(r.live_price)}), so the signal can change until the 3:30 pm close.")
            if (r.partial_bar_excluded) Note("Live price unavailable, so today's forming candle is left out. Signals use completed days only.")
            if (st.state == "IN_POSITION") {
                StatLine("Entry", price(st.entry_price), note = st.entry_date?.let { longDate(it) })
                StatLine("Unrealized", pct(st.unrealized_pct), toneOf(st.unrealized_pct))
                if (!ath) StatLine("Protective stop", if (r.params.use_stop != false) price(st.stop_price) else "Off")
                StatLine("Days held", st.bars_held?.toString() ?: "—")
            }
            if (ath) {
                StatLine("Last close", price(st.close))
                StatLine(dmaLabel, price(st.dma), note = st.pct_above_dma?.let { pct(it) })
                StatLine("Prior ATH", price(st.prior_ath))
                StatLine("To ATH", pct(st.pct_to_ath))
                r.history_start?.let { Text("All-time high measured from ${longDate(it)}, the earliest daily data Kite returned.", style = Wv.small, color = Wv.c.text3) }
            } else {
                StatLine("Last close", price(r.series.lastOrNull()?.close))
                StatLine("UT stop", price(st.ut_stop))
                StatLine("20-EMA", price(st.exit_ema))
            }
        }
    }
    if (ath) {
        item {
            WvCard {
                if (st.state == "IN_POSITION") {
                    Label("Exit rule")
                    Checks(listOf(TrendCheck("dma", "Holding above the $dmaLabel", (st.pct_above_dma ?: 0.0) >= 0, "${pct(st.pct_above_dma)} above · exit on a close below ${price(st.dma)}")))
                } else {
                    Label("Entry rules")
                    Checks(
                        listOf(
                            TrendCheck(
                                "window", "Closed below the $dmaLabel in the last ${r.params.window_bars ?: 200} days", st.in_window == true,
                                st.days_since_below_dma?.let { "$it trading days ago" + (st.window_days_left?.let { d -> " · $d days left" } ?: "") } ?: "No close below the DMA yet",
                            ),
                            TrendCheck("ath", "Close above the prior all-time high", st.prior_ath != null && (st.close ?: 0.0) > st.prior_ath, "${price(st.close)} vs ${price(st.prior_ath)}"),
                        ),
                    )
                    Text(if (st.in_window == true) "Setup active: an ATH break would trigger a buy" else "No setup: waiting for a close below the DMA", style = Wv.small.copy(fontWeight = FontWeight.SemiBold), color = if (st.in_window == true) Wv.c.gain else Wv.c.text3)
                }
            }
        }
    } else if (st.regime_checks.isNotEmpty()) {
        item {
            WvCard {
                Label("Trend filter")
                Checks(st.regime_checks)
                Text(if (st.regime_bullish == true) "Bullish regime: entries allowed" else "Not bullish: no new entries", style = Wv.small.copy(fontWeight = FontWeight.SemiBold), color = if (st.regime_bullish == true) Wv.c.gain else Wv.c.text3)
            }
        }
    }
    item { StrategyPriceChart(r, ath) }
    item {
        WvCard {
            Label("Backtest")
            Text("${longDate(r.test_start)} to ${longDate(r.test_end)} · ${r.bars_tested} days · " + if (ath) "${compact(r.params.capital_per_trade)} per trade · no commission" else "${compact(r.params.initial_capital)} start · ${r.params.commission_pct ?: 0.1}% commission", style = Wv.small, color = Wv.c.text3)
            StatLine("Net return", pct(s.net_profit_pct, 1), toneOf(s.net_profit_pct), signedMoney(s.net_profit) + " on " + compact(s.initial_capital))
            StatLine("Buy and hold", pct(s.buy_hold_return_pct, 1), toneOf(s.buy_hold_return_pct))
            StatLine("CAGR", pct(s.cagr_pct, 1), toneOf(s.cagr_pct), compact(s.final_equity))
            StatLine("Max drawdown", String.format("%.1f%%", -kotlin.math.abs(s.max_drawdown_pct)).replace("-", "−"), Wv.c.loss, "Peak-to-trough equity")
            StatLine("Win rate", s.win_rate_pct?.let { String.format("%.0f%%", it) } ?: "—", note = "${pct(s.avg_win_pct, 1)} avg win · ${pct(s.avg_loss_pct, 1)} avg loss")
            StatLine("Profit factor", s.profit_factor?.let { String.format("%.2f", it) } ?: "—", note = "Gross profit ÷ gross loss")
            StatLine("Closed trades", "${s.total_trades}", note = (if (ath) "${s.signal_exits} on DMA break" else "${s.signal_exits} signal · ${s.stop_exits} stop") + if (s.open_trade) " · 1 open" else "")
            StatLine("Avg hold", s.avg_bars_held?.let { String.format("%.0f days", it) } ?: "—")
            StatLine("Time in market", String.format("%.0f%%", s.exposure_pct), note = "Share of days holding")
        }
    }
    if (r.series.size > 1) {
        item {
            WvCard {
                Label("Equity curve")
                Text("Strategy vs buying and holding over the same period", style = Wv.small, color = Wv.c.text3)
                LineChart(
                    r.series.map { it.date },
                    listOf(Series("Strategy", Wv.c.accent, r.series.map { it.equity }), Series("Buy and hold", Wv.c.text3, r.series.map { it.buy_hold }, dashed = true)),
                    format = { compact(it) },
                )
            }
        }
    }
    if (r.trades.isNotEmpty()) {
        item { TradesList(r.trades, if (ath) "Newest first. Entries and exits fill at the signal day's close; no commission." else "Newest first. Entry and exit prices include 1 tick of slippage; P&L is after commission.") }
    }
    item {
        Text(
            if (ath) "A backtest replays past prices; it is not a forecast or investment advice. The all-time high depends on how far back Kite's data goes and how it adjusts for splits and bonuses, so it can differ from TradingView."
            else "A backtest replays past prices; it is not a forecast or investment advice. Results can differ from TradingView because of price-adjustment differences in the data, and because positions are sized in whole shares bought at the fill price.",
            style = Wv.small, color = Wv.c.text3,
        )
    }
}

/** Every trade, newest first, 40 at a time. */
@Composable
private fun TradesList(trades: List<StrategyTrade>, subtitle: String) {
    var shown by rememberSaveable(trades.size) { mutableIntStateOf(40) }
    val list = trades.reversed()
    WvCard {
        Label("Trades")
        Text(subtitle, style = Wv.small, color = Wv.c.text3)
        list.take(shown).forEach { t ->
            HorizontalDivider(color = Wv.c.border)
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 4.dp)) {
                Column(Modifier.weight(1f)) {
                    Text("${longDate(t.entry_date)} → ${if (t.is_open) "open" else longDate(t.exit_date)}", style = Wv.sub, color = Wv.c.text)
                    Text("${price(t.entry_price)} → ${if (t.is_open) "now" else price(t.exit_price)} · ${days(t.bars_held)} · ${if (t.is_open) "still open" else exitReason(t.exit_reason)}", style = Wv.small, color = Wv.c.text3)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(pct(t.pnl_pct, 1), style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = toneOf(t.pnl_pct))
                    Text(signedMoney(t.pnl), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(t.pnl))
                }
            }
        }
        if (list.size > shown) {
            OutlinedButton(onClick = { shown += 40 }, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Text("Show ${minOf(40, list.size - shown)} more of ${list.size - shown}", color = Wv.c.text)
            }
        }
    }
}

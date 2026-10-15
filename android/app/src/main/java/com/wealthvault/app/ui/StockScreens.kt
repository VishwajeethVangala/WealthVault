package com.wealthvault.app.ui

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
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import com.wealthvault.app.data.MomentumAnalysis
import com.wealthvault.app.data.StrategyResult
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
private fun SymbolPicker(initial: String, picks: List<Pair<String, String>>, busy: Boolean, action: String, onRun: (String) -> Unit) {
    var text by rememberSaveable(initial) { mutableStateOf(initial.substringAfter(':')) }
    val focus = LocalFocusManager.current
    val go = { v: String -> if (v.isNotBlank()) { focus.clearFocus(); onRun(v) } }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                text, { text = it.uppercase() },
                placeholder = { Text("Stock, e.g. INFY or BSE:500209") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, imeAction = ImeAction.Go),
                keyboardActions = KeyboardActions(onGo = { go(text) }),
                modifier = Modifier.weight(1f),
            )
            PrimaryButton(if (busy) "…" else action, busy = busy, enabled = text.isNotBlank()) { go(text) }
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
fun MomentumScreen(vm: AppViewModel, avm: AnalysisViewModel, symbol: String?, onStrategies: (String) -> Unit) {
    val res by avm.momentum.collectAsState()
    val picks = quickPicks(vm, avm)
    LaunchedEffect(symbol) { if (!symbol.isNullOrBlank() && avm.momentum.value.data?.instrument?.endsWith(symbol.substringAfter(':')) != true) avm.analyse(symbol) }
    LaunchedEffect(Unit) { if (avm.signals.value.data == null) avm.loadSignals() }
    val m = res.data

    LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { PageTitle("Momentum", "Trend, returns and strength against the market for any NSE/BSE stock. Prices from Zerodha Kite.") }
        item { SymbolPicker(symbol ?: m?.instrument ?: "", picks, res.loading, "Analyse") { avm.analyse(it) } }
        res.problem?.let { item { ProblemNote(it) } }
        if (res.loading) item { Loading("Reading price history…") }
        if (m != null) momentumBody(m, onStrategies)
        if (m == null && !res.loading && res.problem == null) item { Note("Pick one of your holdings or type a symbol.") }
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.momentumBody(m: MomentumAnalysis, onStrategies: (String) -> Unit) {
    item {
        WvCard {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(m.name ?: m.instrument, style = Wv.title, color = Wv.c.text)
                    Text("${m.instrument} · as of ${longDate(m.as_of)}" + if (m.live_bar) " · live" else "", style = Wv.small, color = Wv.c.text3)
                }
                Text(price(m.last_price), style = Wv.kpi.copy(fontSize = Wv.title.fontSize), color = Wv.c.text)
            }
            val ratio = if (m.trend_max_score > 0) m.trend_score * 5.0 / m.trend_max_score else 0.0
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Badge(m.trend_verdict, if (ratio >= 3.5) Tone.Ok else if (ratio <= 1.5) Tone.Bad else Tone.Warn)
                Text("Trend score ${m.trend_score}/${m.trend_max_score}", style = Wv.sub, color = Wv.c.text2)
            }
            OutlinedButton(onClick = { onStrategies(m.instrument) }, shape = RoundedCornerShape(10.dp)) { Text("Run the strategies on it", color = Wv.c.accent) }
        }
    }
    if (m.series.size > 1) {
        item {
            WvCard {
                Label("Price and moving averages")
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
    item { WvCard { Label("Trend checks"); Checks(m.trend_checks) } }
    item {
        WvCard {
            Label("Returns")
            Row {
                Text("", style = Wv.small, modifier = Modifier.weight(1f))
                Text("Stock", style = Wv.small, color = Wv.c.text3, modifier = Modifier.width(80.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
                Text("vs ${m.benchmark.ifBlank { "market" }}", style = Wv.small, color = Wv.c.text3, modifier = Modifier.width(96.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
            }
            listOf("1M", "3M", "6M", "12M", "12-1").forEach { w ->
                val r = m.returns[w]
                val rs = m.relative_strength[w]
                Row(Modifier.padding(vertical = 2.dp)) {
                    Text(if (w == "12-1") "12M skipping last month" else w, style = Wv.sub, color = Wv.c.text2, modifier = Modifier.weight(1f))
                    Text(pct(r, 1), style = Wv.num, color = toneOf(r), modifier = Modifier.width(80.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
                    Text(if (w == "12-1") "" else pct(rs, 1), style = Wv.num, color = toneOf(rs), modifier = Modifier.width(96.dp), textAlign = androidx.compose.ui.text.style.TextAlign.End)
                }
            }
        }
    }
    item {
        WvCard {
            Label("Levels")
            m.rsi_14?.let { rsi ->
                val (zone, tone) = when {
                    rsi >= 70 -> "Overbought" to Wv.c.warn
                    rsi >= 50 -> "Bullish" to Wv.c.gain
                    rsi > 30 -> "Bearish" to Wv.c.loss
                    else -> "Oversold" to Wv.c.warn
                }
                StatLine("RSI (14)", String.format("%.1f", rsi), tone, zone)
            }
            StatLine("52-week high", price(m.high_52w), note = m.pct_from_52w_high?.let { "${pct(it, 1)} from it" })
            StatLine("52-week low", price(m.low_52w), note = m.pct_from_52w_low?.let { "${pct(it, 1)} above it" })
            StatLine("50-DMA", price(m.sma_50), note = m.pct_from_sma50?.let { "price ${pct(it, 1)}" })
            StatLine("200-DMA", price(m.sma_200), note = m.pct_from_sma200?.let { "price ${pct(it, 1)}" })
            m.cross_state?.let {
                StatLine("50/200 cross", if (it == "golden") "Golden cross" else "Death cross", if (it == "golden") Wv.c.gain else Wv.c.loss, m.days_since_cross?.let { d -> "$d days ago" })
            }
            m.volatility_12m?.let { StatLine("Volatility, 12 months", String.format("%.1f%%", it), note = m.risk_adjusted_12m?.let { r -> "return per unit of risk " + String.format("%.2f", r).replace("-", "−") }) }
        }
    }
    item { Text("A rules-based reading of past prices, not advice.", style = Wv.small, color = Wv.c.text3) }
}

/** The strategies' exit codes in words. */
private fun exitReason(code: String) = when (code) {
    "ATR STOP" -> "stop hit"
    "UT + EMA20 SELL" -> "sell signal"
    "200DMA BREAK" -> "closed under the 200-DMA"
    else -> code.lowercase()
}

// --- strategies ----------------------------------------------------------------------------------------------

@Composable
fun StrategyScreen(vm: AppViewModel, avm: AnalysisViewModel, symbol: String?) {
    var tab by rememberSaveable { mutableStateOf("swing") }
    var current by rememberSaveable { mutableStateOf(symbol.orEmpty()) }
    val swing by avm.swing.collectAsState()
    val ath by avm.ath.collectAsState()
    val res = if (tab == "ath") ath else swing
    val picks = quickPicks(vm, avm)
    LaunchedEffect(symbol) { if (!symbol.isNullOrBlank()) { current = symbol; avm.runStrategy("swing", symbol); avm.runStrategy("ath", symbol) } }
    LaunchedEffect(Unit) { if (avm.signals.value.data == null) avm.loadSignals() }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { PageTitle("Strategies", "Run a strategy on any NSE/BSE stock: today's signal, and a backtest of every past trade. Prices from Zerodha Kite.") }
        item {
            Seg(listOf("swing" to "Swing V2.1", "ath" to "200-DMA ATH breakout"), tab) { t ->
                tab = t
                val r = if (t == "ath") avm.ath.value else avm.swing.value
                if (current.isNotBlank() && r.data == null && !r.loading) avm.runStrategy(t, current)
            }
        }
        item {
            Text(
                if (tab == "ath") "Below the 200-DMA, then a close above the all-time high within the window; held until a close under the 200-DMA."
                else "A 50/200-SMA uptrend filter with UT Bot entries; exits on a UT Bot sell with a close under the 20-EMA, or the ATR stop.",
                style = Wv.small, color = Wv.c.text3,
            )
        }
        item { SymbolPicker(current, picks, res.loading, "Run") { current = it; avm.runStrategy(tab, it) } }
        res.problem?.let { item { ProblemNote(it) } }
        if (res.loading) item { Loading("Running the backtest…") }
        res.data?.let { strategyBody(it, tab == "ath") }
        if (res.data == null && !res.loading && res.problem == null) item { Note("Pick one of your holdings or type a symbol.") }
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.strategyBody(r: StrategyResult, ath: Boolean) {
    val st = r.status
    val s = r.stats
    item {
        WvCard {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(r.name ?: r.instrument, style = Wv.title, color = Wv.c.text)
                    Text("${r.instrument} · ${longDate(r.test_start)} to ${longDate(r.test_end)} · ${r.bars_tested} days", style = Wv.small, color = Wv.c.text3)
                }
            }
            val badge = when {
                st.state == "IN_POSITION" && st.pending_order == "SELL" -> "Sell signal" to Tone.Warn
                st.state == "IN_POSITION" -> "In position" to Tone.Ok
                st.pending_order == "BUY" -> "Buy signal" to Tone.Info
                ath && st.in_window == true -> "Setup active" to Tone.Info
                else -> "No position" to Tone.Off
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Badge(badge.first, badge.second)
                Text(st.headline, style = Wv.sub, color = Wv.c.text)
            }
            if (st.detail.isNotBlank()) Text(st.detail, style = Wv.small, color = Wv.c.text2)
            if (st.state == "IN_POSITION") {
                StatLine("Entry", price(st.entry_price), note = st.entry_date?.let { "${longDate(it)}" + (st.bars_held?.let { b -> " · ${days(b)}" } ?: "") })
                st.unrealized_pct?.let { StatLine("Open gain", pct(it), toneOf(it)) }
                st.stop_price?.let { StatLine("Protective stop", price(it)) }
            }
            if (ath) {
                st.pct_to_ath?.let { StatLine("To the all-time high", weight1(it)) }
                st.window_days_left?.let { StatLine("Days left in the window", "$it") }
            }
        }
    }
    if (!ath && st.regime_checks.isNotEmpty()) item { WvCard { Label("Trend filter"); Checks(st.regime_checks) } }
    if (r.series.size > 1) {
        item {
            WvCard {
                Label("Strategy against buy and hold")
                LineChart(
                    r.series.map { it.date },
                    listOf(Series("Strategy", Wv.c.accent, r.series.map { it.equity }), Series("Buy and hold", Wv.c.text3, r.series.map { it.buy_hold }, dashed = true)),
                    format = { compact(it) },
                )
            }
        }
    }
    item {
        WvCard {
            Label("Backtest")
            StatLine("Net profit", pct(s.net_profit_pct, 1), toneOf(s.net_profit_pct), signedMoney(s.net_profit) + " on " + compact(s.initial_capital))
            StatLine("Buy and hold", pct(s.buy_hold_return_pct, 1), toneOf(s.buy_hold_return_pct))
            StatLine("Yearly (CAGR)", pct(s.cagr_pct, 1), toneOf(s.cagr_pct))
            StatLine("Worst fall", String.format("%.1f%%", -kotlin.math.abs(s.max_drawdown_pct)).replace("-", "−"), Wv.c.loss)
            StatLine("Trades", "${s.total_trades}" + if (s.open_trade) " (1 open)" else "")
            StatLine("Win rate", s.win_rate_pct?.let { String.format("%.0f%%", it) } ?: "—")
            StatLine("Average win / loss", "${pct(s.avg_win_pct, 1)} / ${pct(s.avg_loss_pct, 1)}")
            StatLine("Profit factor", s.profit_factor?.let { String.format("%.2f", it) } ?: "—")
            StatLine("Time in the market", String.format("%.0f%%", s.exposure_pct), note = s.avg_bars_held?.let { String.format("%.0f days a trade on average", it) })
        }
    }
    if (r.trades.isNotEmpty()) {
        item { Label("Trades, latest first") }
        items(r.trades.reversed().take(40), key = { it.entry_date + it.exit_date }) { t ->
            WvCard(padding = 12) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("${longDate(t.entry_date)} → ${if (t.is_open) "open" else longDate(t.exit_date)}", style = Wv.sub, color = Wv.c.text)
                        Text("${price(t.entry_price)} → ${if (t.is_open) "now" else price(t.exit_price)} · ${days(t.bars_held)} · ${if (t.is_open) "still open" else exitReason(t.exit_reason)}", style = Wv.small, color = Wv.c.text3)
                    }
                    Text(pct(t.pnl_pct, 1), style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = toneOf(t.pnl_pct))
                }
            }
        }
        if (r.trades.size > 40) item { Text("Showing the latest 40 of ${r.trades.size} trades.", style = Wv.small, color = Wv.c.text3) }
    }
    item { Text("A backtest of past prices with the strategy's own rules; it is not a forecast or advice.", style = Wv.small, color = Wv.c.text3) }
}

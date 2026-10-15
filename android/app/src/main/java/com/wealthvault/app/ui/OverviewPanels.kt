package com.wealthvault.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.wealthvault.app.data.ASSET_CLASS_LABEL
import com.wealthvault.app.data.HistoryPoint
import com.wealthvault.app.data.RiskResponse
import java.time.LocalDate
import kotlin.math.abs

/** Portfolio value and money invested over time, from the snapshot every sync stores. */
@Composable
fun ValueCard(history: List<HistoryPoint>) {
    var period by rememberSaveable { mutableStateOf(365) }
    val cutoff = LocalDate.now().minusDays(period.toLong()).toString()
    val pts = history.filter { it.date >= cutoff }.sortedBy { it.date }
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) { Label("Value over time") }
            Seg(listOf(30 to "1M", 90 to "3M", 180 to "6M", 365 to "1Y"), period) { period = it }
        }
        if (pts.size < 2) {
            Text("Not enough synced days in this period yet. Each sync adds a day.", style = Wv.sub, color = Wv.c.text3)
        } else {
            // split the change into what the market did and the money you added, so new money is not read as gain
            val change = pts.last().value - pts.first().value
            val added = pts.last().invested - pts.first().invested
            val market = change - added
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(signedMoney(market), style = Wv.title.copy(fontFeatureSettings = "tnum"), color = toneOf(market))
                Text("market ${if (market < 0) "loss" else "gain"} since ${longDate(pts.first().date)}", style = Wv.small, color = Wv.c.text3)
            }
            if (abs(added) >= 1) {
                Text("Value ${signedMoney(change)}, of which ${signedMoney(added)} is money added", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
            }
            LineChart(
                pts.map { it.date },
                listOf(Series("Value", Wv.c.accent, pts.map { it.value }), Series("Invested", Wv.c.text3, pts.map { it.invested }, dashed = true)),
                format = { compact(it) },
                height = 170.dp,
            )
        }
    }
}

private data class Drift(val cls: String, val weight: Double, val target: Double, val move: Double)

/**
 * The asset mix and the targets in one card: each class's value and weight, its target, the rupees that would
 * close the gap at today's total, and a bar with a tick where the target sits.
 */
@Composable
fun AssetMixCard(mix: Map<String, Pair<Double, Double>>, targets: Map<String, Double>, total: Double, onEdit: () -> Unit) {
    val classes = (mix.keys + targets.filterValues { it > 0 }.keys).distinct()
    val rows = classes.map { c ->
        val w = mix[c]?.first ?: 0.0
        val t = targets[c] ?: 0.0
        Drift(c, w, t, (t - w) / 100 * total)
    }.sortedByDescending { maxOf(it.weight, it.target) }
    val max = rows.maxOfOrNull { maxOf(it.weight, it.target) }?.coerceAtLeast(1.0) ?: 1.0
    val has = targets.values.any { it > 0 }
    WvCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Label("Asset mix")
                Text(if (has) "Weight / target, and what closes the gap" else "Set targets to see how far each class has drifted", style = Wv.small, color = Wv.c.text3)
            }
            OutlinedButton(onClick = onEdit, shape = RoundedCornerShape(10.dp)) { Text(if (has) "Targets" else "Set targets", color = Wv.c.text) }
        }
        MixBar(rows.filter { it.weight > 0 }.map { (Wv.c.classColors[it.cls] ?: Wv.c.text3) to it.weight })
        rows.forEach { r ->
            val color = Wv.c.classColors[r.cls] ?: Wv.c.text3
            Column(Modifier.padding(vertical = 3.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(10.dp).clip(CircleShape).background(color))
                    Spacer(Modifier.width(8.dp))
                    Column(Modifier.weight(1f)) {
                        Text(ASSET_CLASS_LABEL[r.cls] ?: r.cls, style = Wv.body, color = Wv.c.text)
                        Text(compact(mix[r.cls]?.second ?: 0.0), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
                    }
                    Text(String.format("%.1f%%", r.weight) + if (r.target > 0) String.format(" / %.0f%%", r.target) else "", style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                    Text(
                        when {
                            r.target <= 0 -> "—"
                            abs(r.move) < 1000 -> "on target"
                            else -> "${if (r.move > 0) "Add" else "Trim"} ${compact(abs(r.move))}"
                        },
                        style = Wv.small.copy(fontFeatureSettings = "tnum", fontWeight = FontWeight.SemiBold),
                        color = if (r.target > 0 && abs(r.move) >= 1000) toneOf(r.move) else Wv.c.text3,
                        textAlign = TextAlign.End,
                        modifier = Modifier.width(96.dp),
                    )
                }
                // the class's weight as a bar, with a tick where its target sits
                if (has) BoxWithConstraints(Modifier.fillMaxWidth().padding(top = 4.dp).height(8.dp).padding(start = 18.dp)) {
                    Box(Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)).background(Wv.c.surface2))
                    Box(Modifier.fillMaxWidth((r.weight / max).toFloat().coerceIn(0f, 1f)).height(6.dp).clip(RoundedCornerShape(3.dp)).background(color))
                    if (r.target > 0) {
                        Box(Modifier.offset(x = maxWidth * (r.target / max).toFloat().coerceIn(0f, 1f) - 1.dp).width(2.dp).fillMaxHeight().background(Wv.c.text))
                    }
                }
            }
        }
        if (has) Text("Add and Trim are rupees at today's total. Selling to rebalance can trigger tax, so treat it as a guide.", style = Wv.small, color = Wv.c.text3)
    }
}

/** Edit the target weight of each asset class; they should add up to 100%. */
@Composable
fun TargetsDialog(classes: List<String>, targets: Map<String, Double>, onSave: (Map<String, Double>) -> Unit, onDismiss: () -> Unit) {
    val values = remember { mutableStateMapOf<String, String>().apply { classes.forEach { c -> put(c, targets[c]?.let { v -> if (v % 1.0 == 0.0) v.toInt().toString() else v.toString() } ?: "") } } }
    val sum = values.values.sumOf { it.toDoubleOrNull() ?: 0.0 }
    val ok = abs(sum - 100) < 0.01
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Wv.c.surface,
        title = { Text("Target allocation", color = Wv.c.text) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                classes.forEach { c ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(ASSET_CLASS_LABEL[c] ?: c, style = Wv.body, color = Wv.c.text, modifier = Modifier.weight(1f))
                        OutlinedTextField(
                            values[c].orEmpty(), { v -> values[c] = v.filter { it.isDigit() || it == '.' }.take(5) },
                            suffix = { Text("%") }, singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                            modifier = Modifier.width(110.dp),
                        )
                    }
                }
                Text(
                    if (ok) "Adds up to 100%." else String.format("Adds up to %.1f%%; make it 100%%.", sum),
                    style = Wv.small, color = if (ok) Wv.c.gain else Wv.c.warn,
                )
            }
        },
        confirmButton = {
            TextButton(enabled = ok, onClick = { onSave(values.mapValues { it.value.toDoubleOrNull() ?: 0.0 }.filterValues { it > 0 }) }) {
                Text("Save", color = if (ok) Wv.c.accent else Wv.c.text3)
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = Wv.c.text2) } },
    )
}

/** How your Indian stocks would have behaved at today's weights. */
@Composable
fun RiskCard(data: RiskResponse) {
    val r = data.risk
    WvCard {
        Label("Risk")
        Text("How your Indian stocks would have behaved at today's weights", style = Wv.small, color = Wv.c.text3)
        if (r == null) {
            Text(
                "Beta and volatility need stored price history for your stocks (${data.measured_stocks} of ${data.total_stocks} have it). Press Refresh signals on the Signals tab once.",
                style = Wv.sub, color = Wv.c.text3,
            )
            return@WvCard
        }
        val varRupees = r.var95_1d_pct / 100 * data.equity_value
        StatLine(
            "Beta vs Nifty", r.beta?.let { String.format("%.2f", it) } ?: "—",
            note = r.beta?.let { if (it > 1.05) "moves more than the market" else if (it < 0.95) "moves less than the market" else "moves with the market" },
        )
        StatLine("Volatility", String.format("%.1f%%", r.volatility_pct), note = String.format("Nifty %.1f%% a year", r.benchmark_volatility_pct))
        StatLine("1-day loss, 95% of days", String.format("−%.2f%%", r.var95_1d_pct), Wv.c.loss, "about ${compact(varRupees)} on your stocks")
        StatLine("Worst fall from a peak", String.format("%.1f%%", r.max_drawdown_pct).replace("-", "−"), Wv.c.loss, "over ${r.days} trading days")
        StatLine("Best / worst day", "${pct(r.best_day_pct)} / ${pct(r.worst_day_pct)}", note = String.format("%.0f%% of days were up", r.positive_days_pct))
        StatLine("Move with the market", r.correlation?.let { String.format("%.2f", it) } ?: "—", note = "1.0 = identical to the Nifty")
        if (r.coverage_pct < 100) Text(String.format("Measured on %.0f%% of your Indian stock value (%d of %d stocks).", r.coverage_pct, data.measured_stocks, data.total_stocks), style = Wv.small, color = Wv.c.text3)
        if (r.high_beta.isNotEmpty()) Text("Highest beta: " + r.high_beta.joinToString(", ") { String.format("%s %.1f", it.name, it.beta) } + ".", style = Wv.small, color = Wv.c.text3)
    }
}

/** The Equity signals at a glance (Indian stocks you hold); tapping opens the Signals tab. */
@Composable
fun SignalsSummaryCard(holdings: List<com.wealthvault.app.data.Holding>, data: com.wealthvault.app.data.SignalsResponse, live: Map<String, com.wealthvault.app.data.StockSignals>, onOpen: () -> Unit) {
    val map = data.symbol_map
    val sigs = data.signals + live
    val rows = buildInstruments(holdings, false).map { inst ->
        val sig = inst.symbols.firstNotNullOfOrNull { map[it] }?.let { sigs[it] }
        Triple(inst, sig, readSignals(sig, inst.ltp))
    }.distinctBy { it.second?.instrument ?: it.first.key }
    if (rows.none { hasAnySignal(it.second) }) return
    val sources = rows.map { (inst, sig, _) -> CallSource(code = inst.key, name = sig?.name ?: inst.sym, held = true, sig = sig, ltp = inst.ltp) }
    val fmt = PriceFmt(false)
    val s2 = latestSessions(sources, 2)
    val buys = buildBuys(sources, s2, 2, fmt, false).count { !it.waiting }
    val sells = buildSells(sources, latestSessions(sources, 7), fmt, false).count { !it.waiting }
    val bear = rows.filter { it.third.alignment == Agreement.AllBear }
    WvCard(Modifier.clickable(onClick = onOpen)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) { Label("Signals on your stocks") }
            Text("Open", style = Wv.small.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.accent)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            listOf(
                Triple("Swing trades", "${rows.count { it.second?.swing?.state == "IN_POSITION" }}", null),
                Triple("ATH trades", "${rows.count { it.second?.ath?.state == "IN_POSITION" }}", null),
                Triple("All bearish", "${bear.size}", if (bear.isNotEmpty()) Wv.c.loss else null),
            ).forEach { (label, value, tone) ->
                Column(Modifier.weight(1f)) {
                    Text(value, style = Wv.title.copy(fontFeatureSettings = "tnum"), color = tone ?: Wv.c.text)
                    Text(label, style = Wv.small, color = Wv.c.text3)
                }
            }
        }
        Text("$buys buy and $sells sell calls in the latest sessions" + if (bear.isNotEmpty()) " · review ${bear.joinToString(", ") { it.first.sym }.take(60)}" else "", style = Wv.small, color = Wv.c.text2)
    }
}

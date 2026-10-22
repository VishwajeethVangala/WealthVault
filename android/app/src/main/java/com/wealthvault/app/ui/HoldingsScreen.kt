package com.wealthvault.app.ui

import android.content.Context
import android.content.Intent
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.FileDownload
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import com.wealthvault.app.data.ASSET_CLASS_LABEL
import com.wealthvault.app.data.Holding
import java.io.File
import java.time.LocalDate

/**
 * Holdings, as on the web (web/src/pages/HoldingsTable.tsx): every instrument merged across brokers with its
 * per-broker breakdown, summary tiles, the shared broker and asset-class filters, gainers or losers, sorting by
 * any column, grouping by asset class with subtotals, and a CSV export.
 */

private enum class HSort(val label: String) { Cur("Value"), Inv("Invested"), PnlPct("P&L %"), DayPct("1D %"), Sym("Name"), Qty("Qty"), Avg("Avg cost"), Ltp("LTP") }

private fun sortValue(p: Position, k: HSort): Comparable<*>? = when (k) {
    HSort.Cur -> p.cur
    HSort.Inv -> p.inv
    HSort.PnlPct -> p.pnlPct
    HSort.DayPct -> p.dayPct
    HSort.Sym -> p.sym.lowercase()
    HSort.Qty -> p.qty
    HSort.Avg -> p.avg
    HSort.Ltp -> p.ltp
}

/** Sorts by a column; rows with no value for it (no day change, say) always go last. */
@Suppress("UNCHECKED_CAST")
private fun sortPositions(list: List<Position>, key: HSort, asc: Boolean): List<Position> =
    list.sortedWith { a, b ->
        val x = sortValue(a, key) as Comparable<Any>?
        val y = sortValue(b, key) as Comparable<Any>?
        when {
            x == null && y == null -> 0
            x == null -> 1
            y == null -> -1
            else -> if (asc) x.compareTo(y) else y.compareTo(x)
        }
    }

private fun classLabel(cls: String) = ASSET_CLASS_LABEL[cls] ?: cls

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HoldingsScreen(vm: AppViewModel, onStock: (String) -> Unit = {}) {
    val holdingsRes by vm.holdings.collectAsState()
    val brokerFilter by vm.brokerFilter.collectAsState()
    val classFilter by vm.classFilter.collectAsState()
    var q by rememberSaveable { mutableStateOf("") }
    var sortKey by rememberSaveable { mutableStateOf(HSort.Cur) }
    var asc by rememberSaveable { mutableStateOf(false) }
    var grouped by rememberSaveable { mutableStateOf(true) }
    var pnl by rememberSaveable { mutableStateOf("all") }
    val expanded = remember { mutableStateListOf<String>() }
    val context = LocalContext.current

    val all = holdingsRes.data.orEmpty()
    val totalValue = all.sumOf { it.current_value }
    // 1. broker -> merge across brokers -> search; class counts come from here so they reflect the other filters
    val searched = remember(all, brokerFilter, q) {
        val needle = q.trim().lowercase()
        buildPositions(applyFilters(all, brokerFilter, emptySet())).filter { p ->
            needle.isEmpty() || p.sym.lowercase().contains(needle) || classLabel(p.cls).lowercase().contains(needle) ||
                p.brokers.any { brokerKeyLabel(it).lowercase().contains(needle) }
        }
    }
    val classCounts = CLASS_ORDER.mapNotNull { c -> searched.count { it.cls == c }.takeIf { it > 0 || c in classFilter }?.let { c to it } }
    val rows = remember(searched, classFilter, pnl, sortKey, asc) {
        var list = if (classFilter.isEmpty()) searched else searched.filter { it.cls in classFilter }
        if (pnl == "gainers") list = list.filter { it.pnl >= 0 }
        if (pnl == "losers") list = list.filter { it.pnl < 0 }
        sortPositions(list, sortKey, asc)
    }
    val totals = totalsOf(rows)
    val coverage = dayCoverage(rows)
    val maxCur = rows.maxOfOrNull { it.cur }?.coerceAtLeast(1.0) ?: 1.0

    PullToRefreshBox(isRefreshing = holdingsRes.loading && all.isNotEmpty(), onRefresh = { vm.refreshAll() }) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = pagePad, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f)) { PageTitle("Holdings", all.map { brokerKeyOf(it.connection_id) }.distinct().size.let { n -> "Merged across $n broker${if (n == 1) "" else "s"} · ${compact(totalValue)}" }) }
                    EyeButton(vm)
                }
            }
            if (holdingsRes.loading && all.isEmpty()) item { Note("Loading holdings…") }
            holdingsRes.error?.let { e ->
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Note("Could not load holdings. $e", bad = true)
                        OutlinedButton(onClick = { vm.refreshAll() }, shape = RoundedCornerShape(10.dp)) { Text("Retry", color = Wv.c.text) }
                    }
                }
            }
            if (all.isNotEmpty()) {
                item {
                    KpiGrid(
                        listOf(
                            Triple("Current value", compact(totals.cur), "${rows.size} holdings shown"),
                            Triple("Invested", compact(totals.inv), "Weighted avg. cost"),
                            Triple("Total P&L", signedCompact(totals.pnl), pct(totals.pnlPct)),
                            Triple("1-day P&L", if (totals.day == null) "—" else signedCompact(totals.day), if (totals.day == null) "No day change reported yet" else pct(totals.dayPct)),
                            Triple("Winners / losers", "${rows.count { it.pnl >= 0 }} / ${rows.count { it.pnl < 0 }}", "Positions above / below cost"),
                        ),
                        listOf(null, null, toneOf(totals.pnl), toneOf(totals.day), null),
                    )
                }
                if (totals.day != null) item { CoverageNote(coverage) }
                item { OutlinedTextField(q, { q = it }, placeholder = { Text("Search symbol, class or broker") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                // class, broker/gainers and sort chips as one group with room between the rows
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Chip("All ${searched.size}", classFilter.isEmpty()) { vm.classFilter.value = emptySet() }
                            if (classFilter.size > 1) Chip("${classFilter.size} classes", true) {}
                            classCounts.forEach { (c, n) -> Chip("${classLabel(c)} $n", classFilter.size == 1 && c in classFilter) { vm.classFilter.value = setOf(c) } }
                        }
                        FilterBar(vm, all, showClasses = false) {
                            Box(Modifier.width(1.dp).height(20.dp).background(Wv.c.border))
                            listOf("all" to "All", "gainers" to "Gainers", "losers" to "Losers").forEach { (k, label) -> Chip(label, pnl == k) { pnl = k } }
                        }
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Sort", style = Wv.small, color = Wv.c.text3)
                            HSort.entries.forEach { k ->
                                val on = sortKey == k
                                Chip(k.label + if (on) (if (asc) " ↑" else " ↓") else "", on) {
                                    if (on) asc = !asc else { sortKey = k; asc = k == HSort.Sym }
                                }
                            }
                        }
                    }
                }
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Switch(
                            grouped, { grouped = it },
                            colors = SwitchDefaults.colors(checkedTrackColor = Wv.c.accent, checkedThumbColor = Wv.c.onAccent, uncheckedTrackColor = Wv.c.surface2, uncheckedThumbColor = Wv.c.text3, uncheckedBorderColor = Wv.c.borderStrong),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text("Group by asset class", style = Wv.sub, color = Wv.c.text2, modifier = Modifier.weight(1f))
                        TextButton(onClick = { exportCsv(context, rows) }, enabled = rows.isNotEmpty()) {
                            Icon(Icons.Outlined.FileDownload, contentDescription = null, tint = Wv.c.accent, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Export CSV", color = Wv.c.accent)
                        }
                    }
                }
                if (rows.isEmpty()) item { Note(if (all.isEmpty()) "No holdings yet. Connect a broker and run a sync." else "No holdings match these filters.") }
                val toggle = { key: String -> if (key in expanded) expanded.remove(key) else expanded.add(key) }
                if (grouped) {
                    CLASS_ORDER.forEach { c ->
                        val items = rows.filter { it.cls == c }
                        if (items.isEmpty()) return@forEach
                        item(key = "g-$c") { GroupHeader(c, items, totalValue) }
                        items(items, key = { it.key }) { p -> PositionCard(p, totalValue, maxCur, p.key in expanded, { toggle(p.key) }, onStock) }
                    }
                } else {
                    items(rows, key = { it.key }) { p -> PositionCard(p, totalValue, maxCur, p.key in expanded, { toggle(p.key) }, onStock) }
                }
                if (rows.isNotEmpty()) {
                    item {
                        WvCard(padding = 12) {
                            Text("Total · ${rows.size} holdings", style = Wv.title, color = Wv.c.text)
                            StatLine("Invested", money(totals.inv))
                            StatLine("Current", money(totals.cur))
                            StatLine("P&L", signedMoney(totals.pnl), toneOf(totals.pnl), pct(totals.pnlPct))
                            StatLine("1-day P&L", if (totals.day == null) "—" else signedMoney(totals.day), toneOf(totals.day), totals.day?.let { pct(totals.dayPct) })
                            StatLine("Share of portfolio", weightPct(if (totalValue > 0) totals.cur / totalValue * 100 else null, 2))
                        }
                    }
                }
                item {
                    Text(
                        "Weight is the share of your total portfolio value across all brokers. Average cost is quantity-weighted across brokers. Day change comes from the brokers; mutual funds and NPS do not report one, so they show a dash and are left out of the 1-day total.",
                        style = Wv.small, color = Wv.c.text3,
                    )
                }
            }
        }
    }
}

@Composable
private fun GroupHeader(cls: String, items: List<Position>, totalValue: Double) {
    val t = totalsOf(items)
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 6.dp, start = 2.dp)) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(Wv.c.classColors[cls] ?: Wv.c.text3))
        Spacer(Modifier.width(6.dp))
        Text("${classLabel(cls).uppercase()} · ${items.size}", style = Wv.over, color = Wv.c.text2, modifier = Modifier.weight(1f))
        Text(compact(t.cur), style = Wv.small.copy(fontFeatureSettings = "tnum", fontWeight = FontWeight.SemiBold), color = Wv.c.text)
        Text("  ${pct(t.pnlPct, 1)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(t.pnl))
        Text("  ${weightPct(if (totalValue > 0) t.cur / totalValue * 100 else null)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
    }
}

/** The small coloured letter tiles naming the brokers that hold a position. */
@Composable
fun BrokerTiles(keys: List<String>) {
    Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
        keys.forEach { k ->
            Box(Modifier.size(16.dp).clip(RoundedCornerShape(4.dp)).background(BROKER_COLORS[k] ?: Wv.c.text3), contentAlignment = Alignment.Center) {
                Text(brokerKeyLabel(k).take(1), style = Wv.small.copy(fontSize = 9.sp, fontWeight = FontWeight.Bold), color = Color.White)
            }
        }
    }
}

@Composable
private fun PositionCard(p: Position, totalValue: Double, maxCur: Double, open: Boolean, onToggle: () -> Unit, onStock: (String) -> Unit) {
    val w = if (totalValue > 0) p.cur / totalValue * 100 else null
    WvCard(Modifier.animateContentSize().clickable(onClick = onToggle), padding = 14) {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Text(p.sym, style = Wv.title, color = Wv.c.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    BrokerTiles(p.brokers)
                    Text("${classLabel(p.cls)} · ${trimQty(p.qty)} @ ${ownPrice(p.avg)}", style = Wv.small, color = Wv.c.text3, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Text("LTP ${ownPrice(p.ltp)} · invested ${money(p.inv)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
            }
            Column(horizontalAlignment = Alignment.End, modifier = Modifier.padding(start = 10.dp)) {
                Text(money(p.cur), style = Wv.num.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                Text("${signedMoney(p.pnl)} · ${pct(p.pnlPct, 1)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(p.pnl))
                Text(if (p.day == null) "1D —" else "1D ${signedMoney(p.day)} · ${pct(p.dayPct, 1)}", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(p.day))
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f).height(4.dp).clip(RoundedCornerShape(2.dp)).background(Wv.c.surface2)) {
                Box(Modifier.fillMaxWidth((p.cur / maxCur).toFloat().coerceIn(0f, 1f)).fillMaxHeight().background(Wv.c.accent))
            }
            Text(weightPct(w, 2), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3, modifier = Modifier.padding(start = 8.dp))
            Icon(if (open) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore, contentDescription = if (open) "Hide the broker breakdown" else "Show the broker breakdown", tint = Wv.c.text3)
        }
        if (open) {
            HorizontalDivider(color = Wv.c.border)
            p.lots.forEach { l ->
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 2.dp)) {
                    BrokerTiles(listOf(l.brokerKey))
                    Spacer(Modifier.width(6.dp))
                    Column(Modifier.weight(1f)) {
                        Text(brokerKeyLabel(l.brokerKey), style = Wv.sub, color = Wv.c.text)
                        Text("${trimQty(l.qty)} @ ${ownPrice(l.holding.average_price)} · invested ${money(l.inv)} · ${if (p.qty > 0) "${Math.round(l.qty / p.qty * 100)}%" else "—"} of the position", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
                    }
                    Column(horizontalAlignment = Alignment.End, modifier = Modifier.padding(start = 10.dp)) {
                        Text(money(l.cur), style = Wv.small.copy(fontFeatureSettings = "tnum", fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                        Text("${signedMoney(l.pnl)} (${pct(if (l.inv > 0) l.pnl / l.inv * 100 else null, 1)})", style = Wv.small.copy(fontFeatureSettings = "tnum"), color = toneOf(l.pnl))
                    }
                }
            }
            Text(
                "LTP ${ownPrice(p.ltp)} · day change ${pct(p.dayPct)} · price ${when (p.freshness) { "live" -> "live"; "cached" -> "stored (not live)"; else -> "partly live" }}",
                style = Wv.small, color = Wv.c.text3,
            )
            p.stockSymbol?.let { s -> TextButton(onClick = { onStock(s) }) { Text("Open in Momentum", color = Wv.c.accent) } }
        }
    }
}

/** The rows shown, one line per broker lot, as a CSV file handed to the share sheet (the web downloads the same file). */
private fun exportCsv(context: Context, rows: List<Position>) {
    val esc = { v: Any -> "\"" + v.toString().replace("\"", "\"\"") + "\"" }
    val header = listOf("Symbol", "Asset class", "Broker", "Quantity", "Avg cost", "LTP", "Invested", "Current value", "P&L", "P&L %", "1D P&L")
    val lines = rows.flatMap { p ->
        p.lots.map { l ->
            listOf(
                p.sym, classLabel(p.cls), brokerKeyLabel(l.brokerKey), l.qty, String.format("%.2f", l.holding.average_price), String.format("%.2f", p.ltp),
                String.format("%.2f", l.inv), String.format("%.2f", l.cur), String.format("%.2f", l.pnl),
                if (l.inv > 0) String.format("%.2f", l.pnl / l.inv * 100) else "", l.day?.let { String.format("%.2f", it) } ?: "",
            ).joinToString(",") { esc(it) }
        }
    }
    val dir = File(context.cacheDir, "exports").apply { mkdirs() }
    val file = File(dir, "holdings_${LocalDate.now()}.csv")
    file.writeText((listOf(header.joinToString(",") { esc(it) }) + lines).joinToString("\n"))
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "text/csv"
        putExtra(Intent.EXTRA_STREAM, uri)
        putExtra(Intent.EXTRA_SUBJECT, "WealthVault holdings ${LocalDate.now()}")
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(send, "Export holdings"))
}

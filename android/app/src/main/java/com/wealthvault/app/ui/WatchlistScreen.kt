package com.wealthvault.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ShowChart
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.CandlestickChart
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.wealthvault.app.data.StockSuggestion
import com.wealthvault.app.data.WatchlistItem
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private enum class WatchlistFilter(val label: String) {
    All("All"),
    Bullish("Bullish"),
    Setups("In Setup / Trade"),
    Bearish("Bearish"),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WatchlistScreen(
    vm: AppViewModel,
    avm: AnalysisViewModel,
    modifier: Modifier = Modifier,
    onStock: (kind: String, symbol: String) -> Unit = { _, _ -> },
) {
    val watchlistRes by vm.watchlist.collectAsState()
    val allItems = watchlistRes.data.orEmpty()
    var filter by rememberSaveable { mutableStateOf(WatchlistFilter.All) }
    var searchInput by rememberSaveable { mutableStateOf("") }
    var suggestions by remember { mutableStateOf<List<StockSuggestion>>(emptyList()) }
    var searching by remember { mutableStateOf(false) }
    var isAdding by remember { mutableStateOf(false) }
    var isRefreshing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        vm.loadWatchlist()
    }

    // Debounced search for Kite symbols
    var searchJob by remember { mutableStateOf<Job?>(null) }
    LaunchedEffect(searchInput) {
        searchJob?.cancel()
        val q = searchInput.trim()
        if (q.length < 2) {
            suggestions = emptyList()
            searching = false
            return@LaunchedEffect
        }
        searching = true
        searchJob = scope.launch {
            delay(300)
            suggestions = avm.suggest(q).take(6)
            searching = false
        }
    }

    // Filter logic
    val filtered = remember(allItems, filter) {
        when (filter) {
            WatchlistFilter.All -> allItems
            WatchlistFilter.Bullish -> allItems.filter {
                it.trend_score != null && it.trend_score >= 4
            }
            WatchlistFilter.Setups -> allItems.filter {
                it.ath_breakout_state == "SETUP_ACTIVE" || it.ath_breakout_state == "IN_POSITION"
            }
            WatchlistFilter.Bearish -> allItems.filter {
                it.trend_score != null && it.trend_score <= 2
            }
        }
    }

    // KPI Metrics calculation
    val trackedCount = allItems.size
    val bullishCount = allItems.count { it.trend_score != null && it.trend_score >= 4 }
    val athCount = allItems.count { it.ath_breakout_state == "SETUP_ACTIVE" || it.ath_breakout_state == "IN_POSITION" }
    val avgGain = remember(allItems) {
        val validReturns = allItems.mapNotNull { it.return_pct }
        if (validReturns.isNotEmpty()) validReturns.average() else 0.0
    }

    PullToRefreshBox(
        isRefreshing = watchlistRes.loading && allItems.isNotEmpty(),
        onRefresh = { vm.refreshWatchlist() },
        modifier = modifier.fillMaxSize(),
    ) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = pagePad,
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            // Header Row with Title and Refresh Action
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        PageTitle("Watchlist", "Pre-flight radar: momentum & breakout signals for prospect stocks")
                    }
                    IconButton(
                        onClick = {
                            isRefreshing = true
                            vm.refreshWatchlist()
                            scope.launch {
                                delay(1000)
                                isRefreshing = false
                            }
                        },
                        enabled = !isRefreshing,
                    ) {
                        if (isRefreshing) {
                            CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp, color = Wv.c.accent)
                        } else {
                            Icon(Icons.Outlined.Refresh, contentDescription = "Refresh Signals", tint = Wv.c.text2)
                        }
                    }
                }
            }

            // Top KPI Summary Cards Row
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    KpiTile("Tracked", "$trackedCount", "Prospect radar", modifier = Modifier.weight(1f))
                    KpiTile("Bullish", "$bullishCount", "Score \u2265 4/5", valueTone = if (bullishCount > 0) Wv.c.gain else Wv.c.text, modifier = Modifier.weight(1f))
                    KpiTile("ATH Breakouts", "$athCount", "In setup / trade", valueTone = if (athCount > 0) Wv.c.accent else Wv.c.text, modifier = Modifier.weight(1f))
                    KpiTile("Avg Gain", pct(avgGain), "Since added", valueTone = toneOf(avgGain), modifier = Modifier.weight(1f))
                }
            }

            // Quick Add Stock Search Card
            item {
                WvCard(padding = 12) {
                    Text("ADD STOCK TO RADAR", style = Wv.over, color = Wv.c.text3)
                    Spacer(Modifier.height(4.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        OutlinedTextField(
                            value = searchInput,
                            onValueChange = { searchInput = it },
                            placeholder = { Text("Search ticker or name (e.g. TCS, RELIANCE)", style = Wv.sub, color = Wv.c.text3) },
                            singleLine = true,
                            leadingIcon = { Icon(Icons.Outlined.Search, contentDescription = null, tint = Wv.c.text3) },
                            modifier = Modifier.weight(1f),
                        )
                        Button(
                            onClick = {
                                if (searchInput.isNotBlank()) {
                                    isAdding = true
                                    val target = searchInput.trim().uppercase()
                                    vm.toggleWatch(target) {
                                        isAdding = false
                                        searchInput = ""
                                        suggestions = emptyList()
                                    }
                                }
                            },
                            enabled = searchInput.isNotBlank() && !isAdding,
                            colors = ButtonDefaults.buttonColors(containerColor = Wv.c.accent),
                            shape = RoundedCornerShape(10.dp),
                        ) {
                            if (isAdding) {
                                CircularProgressIndicator(modifier = Modifier.size(16.dp), color = Wv.c.text, strokeWidth = 2.dp)
                            } else {
                                Icon(Icons.Outlined.Add, contentDescription = "Add", modifier = Modifier.size(18.dp))
                            }
                        }
                    }

                    // Autocomplete Suggestions Dropdown
                    if (suggestions.isNotEmpty()) {
                        Spacer(Modifier.height(8.dp))
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(8.dp))
                                .background(Wv.c.surface2)
                                .padding(vertical = 4.dp),
                        ) {
                            suggestions.forEach { s ->
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable {
                                            isAdding = true
                                            val sym = s.symbol
                                            vm.toggleWatch(sym) {
                                                isAdding = false
                                                searchInput = ""
                                                suggestions = emptyList()
                                            }
                                        }
                                        .padding(horizontal = 12.dp, vertical = 8.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Column(Modifier.weight(1f)) {
                                        Text(s.symbol, style = Wv.sub.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
                                        if (s.name.isNotBlank()) {
                                            Text(s.name, style = Wv.small, color = Wv.c.text3, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        }
                                    }
                                    Text("+ Add", style = Wv.small.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.accent)
                                }
                            }
                        }
                    }
                }
            }

            // Filter Pills
            item {
                Seg(
                    options = WatchlistFilter.entries.map { it to it.label },
                    selected = filter,
                    modifier = Modifier.fillMaxWidth(),
                ) { filter = it }
            }

            // Empty state
            if (filtered.isEmpty() && !watchlistRes.loading) {
                item {
                    WvCard {
                        Text(
                            if (allItems.isEmpty()) "No prospect stocks tracked yet.\nSearch above to add stocks to your pre-flight radar."
                            else "No stocks match the \"${filter.label}\" filter.",
                            style = Wv.sub,
                            color = Wv.c.text3,
                            modifier = Modifier.padding(vertical = 12.dp),
                        )
                    }
                }
            }

            // Watchlist Stock Cards
            items(filtered, key = { it.symbol }) { item ->
                WatchlistCard(
                    item = item,
                    onMomentum = { onStock("momentum", item.symbol) },
                    onStrategy = { onStock("strategy", item.symbol) },
                    onRemove = { vm.toggleWatch(item.symbol) },
                )
            }
        }
    }
}

@Composable
private fun KpiTile(label: String, value: String, foot: String, valueTone: androidx.compose.ui.graphics.Color = Wv.c.text, modifier: Modifier = Modifier) {
    WvCard(modifier, padding = 10) {
        Text(label, style = Wv.small.copy(fontSize = 10.sp), color = Wv.c.text3, maxLines = 1)
        Text(value, style = Wv.kpi.copy(fontSize = 16.sp, fontWeight = FontWeight.Bold), color = valueTone, maxLines = 1)
        Text(foot, style = Wv.small.copy(fontSize = 9.sp), color = Wv.c.text3, maxLines = 1)
    }
}

@Composable
private fun WatchlistCard(
    item: WatchlistItem,
    onMomentum: () -> Unit,
    onStrategy: () -> Unit,
    onRemove: () -> Unit,
) {
    WvCard(padding = 12) {
        // Top row: Symbol, Name, Price, and Return
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Top,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    item.symbol.substringAfter(':'),
                    style = Wv.title.copy(fontSize = 16.sp, fontWeight = FontWeight.Bold),
                    color = Wv.c.text,
                )
                Text(
                    item.name ?: item.symbol,
                    style = Wv.small,
                    color = Wv.c.text3,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    price(item.last_price),
                    style = Wv.num.copy(fontWeight = FontWeight.Bold, fontSize = 15.sp),
                    color = Wv.c.text,
                )
                val ret = item.return_pct
                if (ret != null) {
                    Text(
                        "${if (ret >= 0) "+" else ""}${pct(ret)}",
                        style = Wv.small.copy(fontWeight = FontWeight.SemiBold),
                        color = toneOf(ret),
                    )
                } else if (item.entry_price != null) {
                    Text(
                        "added @ ${price(item.entry_price)}",
                        style = Wv.small.copy(fontSize = 10.sp),
                        color = Wv.c.text3,
                    )
                }
            }
        }

        Spacer(Modifier.height(8.dp))

        // Middle Row: Trend verdict & ATH breakout badges
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            val verdict = item.trend_verdict
            val score = item.trend_score
            if (!verdict.isNullOrBlank()) {
                val tone = when {
                    score != null && score >= 4 -> Tone.Ok
                    score != null && score <= 2 -> Tone.Bad
                    else -> Tone.Off
                }
                val label = if (score != null) "$verdict ($score/5)" else verdict
                Badge(label, tone)
            } else {
                Badge("Pending scan", Tone.Off)
            }

            val athState = item.ath_breakout_state
            when (athState) {
                "SETUP_ACTIVE" -> Badge("Setup active", Tone.Warn)
                "IN_POSITION" -> Badge("In position", Tone.Ok)
                else -> Badge("No setup", Tone.Off)
            }

            Spacer(Modifier.weight(1f))

            // Action Buttons
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                IconButton(onClick = onMomentum, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.AutoMirrored.Outlined.ShowChart, contentDescription = "Momentum", tint = Wv.c.accent, modifier = Modifier.size(18.dp))
                }
                IconButton(onClick = onStrategy, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Outlined.CandlestickChart, contentDescription = "ATH Strategy", tint = Wv.c.accent, modifier = Modifier.size(18.dp))
                }
                IconButton(onClick = onRemove, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Outlined.Delete, contentDescription = "Remove", tint = Wv.c.loss, modifier = Modifier.size(18.dp))
                }
            }
        }
    }
}

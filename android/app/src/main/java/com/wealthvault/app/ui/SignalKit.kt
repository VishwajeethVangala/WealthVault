package com.wealthvault.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.unit.dp
import com.wealthvault.app.data.AthSignal
import com.wealthvault.app.data.MomentumSignal
import com.wealthvault.app.data.StockSignals
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import kotlin.math.abs

/**
 * The web app's reading of a stock's two signals (web/src/components/signals/signalKit.tsx), shared by the
 * Equity signals and Stage 2 screens: which way each leans, whether they agree, and the move since entry.
 */

enum class Lean { Bull, Bear, Neutral }

enum class Agreement(val order: Int) { AllBull(3), Mixed(2), None(1), AllBear(0) }

fun momentumLean(m: MomentumSignal) = when {
    Regex("uptrend", RegexOption.IGNORE_CASE).containsMatchIn(m.verdict) -> Lean.Bull
    Regex("downtrend", RegexOption.IGNORE_CASE).containsMatchIn(m.verdict) -> Lean.Bear
    else -> Lean.Neutral
}

fun athLean(a: AthSignal) = when {
    a.state == "IN_POSITION" -> Lean.Bull
    a.last_signal == "SELL" -> Lean.Bear
    else -> Lean.Neutral
}

fun momentumBadge(m: MomentumSignal): Pair<String, Tone> = m.verdict to when (momentumLean(m)) {
    Lean.Bull -> Tone.Ok
    Lean.Bear -> Tone.Bad
    Lean.Neutral -> Tone.Off
}

fun athBadge(a: AthSignal): Pair<String, Tone> = when {
    a.state == "IN_POSITION" -> "In position" to Tone.Ok
    a.last_signal == "SELL" -> "Exited" to Tone.Warn
    a.in_window -> "Setup active" to Tone.Info
    else -> "No setup" to Tone.Off
}

data class Since(val pct: Double, val abs: Double)

fun since(entry: Double?, ltp: Double): Since? =
    if (entry != null && entry > 0 && ltp > 0) Since((ltp - entry) / entry * 100, ltp - entry) else null

data class Reading(val bull: Int, val bear: Int, val alignment: Agreement, val athSince: Since?)

/** Combine a stock's signals with its live price into the alignment and since-entry figures. */
fun readSignals(sig: StockSignals?, ltp: Double): Reading {
    val leans = listOfNotNull(sig?.momentum?.let(::momentumLean), sig?.ath?.let(::athLean))
    val bull = leans.count { it == Lean.Bull }
    val bear = leans.count { it == Lean.Bear }
    val alignment = when {
        leans.size < 2 -> Agreement.None
        bull == leans.size -> Agreement.AllBull
        bear == leans.size -> Agreement.AllBear
        else -> Agreement.Mixed
    }
    return Reading(
        bull, bear, alignment,
        athSince = if (sig?.ath?.state == "IN_POSITION") since(sig.ath.entry_price, ltp) else null,
    )
}

fun hasAnySignal(sig: StockSignals?) = sig != null && (sig.momentum != null || sig.ath != null)

/** Prices in the stock's own currency: rupees for India, dollars for US stocks. */
class PriceFmt(val usd: Boolean) {
    fun price(v: Double?): String = when {
        v == null || v.isNaN() -> "—"
        usd -> (if (v < 0) "−" else "") + "$" + String.format("%,.2f", abs(v))
        else -> com.wealthvault.app.ui.price(v)
    }

    fun perShare(v: Double): String = (if (v < 0) "−" else "+") + (if (usd) "$" + String.format("%,.2f", abs(v)) else com.wealthvault.app.ui.price(abs(v)))
}

private val isoDate = DateTimeFormatter.ISO_LOCAL_DATE
private val dayMonth = DateTimeFormatter.ofPattern("d MMM")
private val dayMonthYear = DateTimeFormatter.ofPattern("d MMM yyyy")
private val weekdayDayMonth = DateTimeFormatter.ofPattern("EEE d MMM")

private fun parseDay(iso: String?): LocalDate? = iso?.takeIf { it.length >= 10 }?.let { runCatching { LocalDate.parse(it.take(10), isoDate) }.getOrNull() }

/** 6 Oct */
fun shortDate(iso: String?): String = parseDay(iso)?.format(dayMonth) ?: "—"

/** 6 Oct 2026 */
fun longDate(iso: String?): String = parseDay(iso)?.format(dayMonthYear) ?: "—"

/** Tue 6 Oct */
fun weekdayDate(iso: String?): String = parseDay(iso)?.format(weekdayDayMonth) ?: "—"

/** "today", "1 day", "5 days" for a count of trading days held */
fun days(n: Int): String = when (n) {
    0 -> "today"
    1 -> "1 day"
    else -> "$n days"
}

/** +4.2% with one decimal; a dash for unknown */
fun signed1(v: Double?): String = if (v == null) "—" else (if (v < 0) "−" else "+") + String.format("%.1f%%", abs(v))

/** 4.2% without a sign */
fun weight1(v: Double?): String = if (v == null) "—" else String.format("%.1f%%", abs(v))

// --- building blocks for a stock's signal block -----------------------------------------------------------

/** One signal: its badge on the left, its explanation lines under it. */
@Composable
fun SignalLine(label: String, badge: Pair<String, Tone>?, lines: List<Pair<String, androidx.compose.ui.graphics.Color?>>, missing: String = "—") {
    Column(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, style = Wv.small, color = Wv.c.text3, modifier = Modifier.width(92.dp))
            if (badge != null) Badge(badge.first, badge.second) else Text(missing, style = Wv.small, color = Wv.c.text3)
        }
        lines.forEach { (t, color) ->
            Text(t, style = Wv.small.copy(fontFeatureSettings = "tnum"), color = color ?: Wv.c.text3, modifier = Modifier.padding(start = 92.dp))
        }
    }
}

/** Where today's price sits in the 52-week range: a track with a dot. */
@Composable
fun RangeBar(pos: Double, modifier: Modifier = Modifier) {
    val p = (pos / 100).coerceIn(0.0, 1.0).toFloat()
    Box(modifier.fillMaxWidth().height(10.dp), contentAlignment = Alignment.CenterStart) {
        Box(Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)).background(Wv.c.surface2))
        Layout(content = { Box(Modifier.size(10.dp).clip(CircleShape).background(Wv.c.accent)) }, modifier = Modifier.fillMaxWidth()) { m, c ->
            val dot = m.first().measure(c.copy(minWidth = 0, minHeight = 0))
            layout(c.maxWidth, dot.height) { dot.place(((c.maxWidth - dot.width) * p).toInt(), 0) }
        }
    }
}

/** The two signals and their agreement, as the web app's table row shows them, stacked for a phone. */
@Composable
fun SignalBlock(sig: StockSignals?, ltp: Double, reading: Reading, fmt: PriceFmt) {
    val err = { key: String -> sig?.errors?.get(key) ?: sig?.errors?.get("all") ?: "—" }
    Column {
        val m = sig?.momentum
        SignalLine(
            "Momentum",
            m?.let(::momentumBadge),
            if (m == null) emptyList() else listOfNotNull(
                "Score ${m.score}/${m.max}" + (m.pct_from_52w_high?.let { " · ${pct(it, 1)} from 52W high" } ?: "") to null,
            ),
            err("momentum"),
        )
        if (m?.range_pos != null) {
            Row { Spacer(Modifier.width(92.dp)); RangeBar(m.range_pos, Modifier.width(140.dp)) }
        }
        Spacer(Modifier.height(6.dp))
        val a = sig?.ath
        SignalLine(
            "ATH breakout",
            a?.let(::athBadge),
            when {
                a == null -> emptyList()
                a.state == "IN_POSITION" -> listOfNotNull(
                    "Entered ${longDate(a.entry_date)}" + (a.bars_held?.let { " · ${days(it)}" } ?: "") to null,
                    reading.athSince?.let { "${fmt.perShare(it.abs)}/sh (${pct(it.pct)}) since entry" to toneOf(it.abs) },
                    a.pct_above_dma?.let { "${weight1(it)} above 200-DMA" to null },
                )
                a.in_window -> listOf(listOfNotNull(a.window_days_left?.let { "${days(it)} left" }, a.pct_to_ath?.let { "${weight1(it)} to ATH" }).joinToString(" · ") to null)
                else -> listOf(a.headline to null)
            },
            err("ath"),
        )
        Spacer(Modifier.height(6.dp))
        SignalLine(
            "Agreement",
            when (reading.alignment) {
                Agreement.AllBull -> "All bullish" to Tone.Ok
                Agreement.AllBear -> "All bearish" to Tone.Bad
                Agreement.Mixed -> "Mixed" to Tone.Off
                Agreement.None -> null
            },
            if (reading.alignment == Agreement.None) emptyList() else listOf("${reading.bull} bullish · ${reading.bear} bearish" to null),
            if (sig != null) "Too few signals" else "—",
        )
    }
}

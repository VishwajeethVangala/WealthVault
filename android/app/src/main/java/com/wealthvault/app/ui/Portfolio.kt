package com.wealthvault.app.ui

import com.wealthvault.app.data.BrokerSession
import com.wealthvault.app.data.Holding
import com.wealthvault.app.data.HistoryPoint
import java.time.LocalDate

/**
 * The web app's portfolio model (web/src/components/holdings/holdingsModel.ts, utils/portfolioFilters.ts,
 * components/dashboard/metrics.ts) on the phone: holdings merged across brokers into positions, the canonical
 * asset classes, totals, per-class cards, concentration, drawdown and drift. Same rules, same numbers.
 */

/** The asset classes in the order every page lists them. */
val CLASS_ORDER = listOf("EQUITY", "MUTUAL_FUND", "US_STOCKS", "GOLD", "NPS", "DEBT", "OTHER")

/** A single holding above this share of the portfolio is flagged as concentrated. */
const val SINGLE_POSITION_LIMIT_PCT = 10.0

/** The class a holding is shown under (gold bonds are gold, debt-like funds are debt), as on the web. */
fun classOf(h: Holding): String {
    val sym = h.instrument_symbol.uppercase()
    val cls = h.asset_class.uppercase()
    return when {
        // before the keyword rules: "Sovereign Gold Bond 2029" contains BOND but is gold
        cls == "GOLD" || "SGB" in sym -> "GOLD"
        cls == "NPS" -> "NPS"
        cls == "US_STOCKS" || h.currency.equals("USD", ignoreCase = true) -> "US_STOCKS"
        cls == "MUTUAL_FUND" -> "MUTUAL_FUND"
        cls == "DEBT" || listOf("DEBT", "LIQUID", "BOND", "GILT", "TREASURY", "ARBITRAGE", "FD", "CASH", "OVERNIGHT").any { it in sym } -> "DEBT"
        cls == "EQUITY" -> "EQUITY"
        else -> "OTHER"
    }
}

/** "conn_zerodha_live" -> "zerodha" */
fun brokerKeyOf(connectionId: String?): String =
    Regex("^conn_([a-z0-9]+)_").find((connectionId ?: "").lowercase())?.groupValues?.get(1).orEmpty()

private val BROKER_NAMES = mapOf("zerodha" to "Zerodha", "indmoney" to "INDmoney", "groww" to "Groww", "angelone" to "Angel One", "upstox" to "Upstox", "dhan" to "Dhan")

/** "zerodha" -> "Zerodha" */
fun brokerKeyLabel(key: String): String = BROKER_NAMES[key] ?: key.replaceFirstChar(Char::uppercase).ifBlank { "Unknown" }

/** Day P&L in rupees, or null when the broker reported none. */
fun dayPnlOf(h: Holding): Double? = h.day_pnl ?: h.day_change?.let { h.quantity * it }

/** Day change %, or null when unknown. */
fun dayPctOf(h: Holding): Double? {
    h.day_change_percentage?.let { return it }
    val pnl = dayPnlOf(h) ?: return null
    val prev = h.current_value - pnl
    return if (prev > 0) pnl / prev * 100 else null
}

/** INDmoney symbols read "CODE (Company Name)"; the name in brackets is what is shown. */
fun displaySymbol(h: Holding): String {
    val sym = h.instrument_symbol
    return (Regex("""\((.+)\)\s*$""").find(sym)?.groupValues?.get(1) ?: sym).trim()
}

/** One broker's lot of a position. */
data class Lot(val holding: Holding, val brokerKey: String, val qty: Double, val inv: Double, val cur: Double, val pnl: Double, val day: Double?)

/** The same instrument merged across brokers. */
data class Position(
    val key: String,
    val sym: String,
    val cls: String,
    val lots: List<Lot>,
    val brokers: List<String>,
    val qty: Double,
    val inv: Double,
    val cur: Double,
    val pnl: Double,
    val day: Double?,
    val dayPct: Double?,
    /** "live", "cached" or "mixed" */
    val freshness: String,
) {
    val avg get() = if (qty > 0) inv / qty else 0.0
    val ltp get() = if (qty > 0) cur / qty else 0.0
    val pnlPct: Double? get() = if (inv > 0) pnl / inv * 100 else null
    /** an Indian stock with an exchange ticker, so its Momentum page can be opened */
    val stockSymbol: String? get() = lots.first().holding.instrument_symbol.let { s ->
        if (cls == "EQUITY" && !tickerOf(s).startsWith("INDS")) tickerOf(s) else null
    }
}

fun buildPositions(holdings: List<Holding>): List<Position> =
    holdings.groupBy { "${classOf(it)}|${displaySymbol(it).uppercase()}" }.map { (key, hs) ->
        val lots = hs.map { h ->
            val inv = h.quantity * h.average_price
            Lot(h, brokerKeyOf(h.connection_id), h.quantity, inv, h.current_value, h.pnl ?: (h.current_value - inv), dayPnlOf(h))
        }
        val reporting = lots.filter { it.day != null }
        val day = if (reporting.isNotEmpty()) reporting.sumOf { it.day!! } else null
        val dayBase = reporting.sumOf { it.cur - it.day!! }
        val live = hs.count { it.data_freshness == "live" }
        Position(
            key = key,
            sym = displaySymbol(hs.first()),
            cls = classOf(hs.first()),
            lots = lots,
            brokers = lots.map { it.brokerKey }.distinct(),
            qty = lots.sumOf { it.qty },
            inv = lots.sumOf { it.inv },
            cur = lots.sumOf { it.cur },
            pnl = lots.sumOf { it.pnl },
            day = day,
            dayPct = if (day != null && dayBase > 0) day / dayBase * 100 else null,
            freshness = if (live == hs.size) "live" else if (live == 0) "cached" else "mixed",
        )
    }

/** The broker and asset-class filters, shared by the Overview and Holdings (the web keeps them in the URL). */
fun applyFilters(holdings: List<Holding>, brokers: Set<String>, classes: Set<String>): List<Holding> =
    holdings.filter { h ->
        (brokers.isEmpty() || brokerKeyOf(h.connection_id) in brokers) && (classes.isEmpty() || classOf(h) in classes)
    }

data class Totals(val cur: Double, val inv: Double, val pnl: Double, val pnlPct: Double?, val day: Double?, val dayPct: Double?, val reporting: Int)

fun totalsOf(positions: List<Position>): Totals {
    val cur = positions.sumOf { it.cur }
    val inv = positions.sumOf { it.inv }
    val rep = positions.filter { it.day != null }
    val day = rep.sumOf { it.day!! }
    val base = rep.sumOf { it.cur - it.day!! }
    return Totals(
        cur, inv, cur - inv, if (inv > 0) (cur - inv) / inv * 100 else null,
        if (rep.isNotEmpty()) day else null, if (rep.isNotEmpty() && base > 0) day / base * 100 else null, rep.size,
    )
}

// --- periods and the value history ---------------------------------------------------------------------

enum class Period(val label: String, val long: String) {
    D1("1D", "today"), W1("1W", "the last week"), M1("1M", "the last month"), M3("3M", "the last 3 months"), YTD("YTD", "this year"), ALL("All", "since you started")
}

private fun startOf(p: Period): String? {
    val d = LocalDate.now()
    return when (p) {
        Period.D1 -> null
        Period.YTD -> "${d.year}-01-01"
        Period.ALL -> "0000-00-00"
        Period.W1 -> d.minusDays(7).toString()
        Period.M1 -> d.minusDays(30).toString()
        Period.M3 -> d.minusDays(91).toString()
    }
}

/** The snapshot to measure from: the last one on or before the period start, else the earliest there is. */
fun baseline(history: List<HistoryPoint>, p: Period): HistoryPoint? {
    val from = startOf(p) ?: return null
    if (history.isEmpty()) return null
    return history.lastOrNull { it.date <= from } ?: history.first()
}

/** The days the hero chart shows: the period, or the last month for "today". */
fun chartWindow(history: List<HistoryPoint>, p: Period): List<HistoryPoint> {
    val from = baseline(history, if (p == Period.D1) Period.M1 else p) ?: return history
    return history.filter { it.date >= from.date }
}

// --- per-class cards ---------------------------------------------------------------------------------------

data class ClassCard(
    val cls: String,
    val items: List<Position>,
    val cur: Double,
    val inv: Double,
    val weight: Double,
    val pnl: Double,
    val pnlPct: Double?,
    val day: Double?,
    val dayPct: Double?,
    /** value change over the chosen period from the daily snapshots (includes money added) */
    val change: Double?,
    val spark: List<Double>,
    val best: Position?,
    val worst: Position?,
)

fun classCards(positions: List<Position>, history: List<HistoryPoint>, fromDate: String?, totalCur: Double): List<ClassCard> =
    CLASS_ORDER.mapNotNull { cls ->
        val items = positions.filter { it.cls == cls }
        val cur = items.sumOf { it.cur }
        if (items.isEmpty() || cur <= 0) return@mapNotNull null
        val inv = items.sumOf { it.inv }
        val rep = items.filter { it.day != null }
        val day = rep.sumOf { it.day!! }
        val base = rep.sumOf { it.cur - it.day!! }
        val series = history.mapNotNull { p -> p.classes[cls]?.let { p.date to it } }
        val then = fromDate?.let { f -> series.lastOrNull { it.first <= f } ?: series.firstOrNull() }
        val ranked = rep.sortedByDescending { it.day!! }
        ClassCard(
            cls, items, cur, inv,
            weight = if (totalCur > 0) cur / totalCur * 100 else 0.0,
            pnl = cur - inv,
            pnlPct = if (inv > 0) (cur - inv) / inv * 100 else null,
            day = if (rep.isNotEmpty()) day else null,
            dayPct = if (rep.isNotEmpty() && base > 0) day / base * 100 else null,
            change = if (then != null && series.isNotEmpty()) series.last().second - then.second else null,
            spark = series.takeLast(30).map { it.second },
            best = ranked.firstOrNull()?.takeIf { it.day!! > 0 },
            worst = ranked.lastOrNull()?.takeIf { it.day!! < 0 },
        )
    }.sortedByDescending { it.cur }

data class Concentration(val top1: Position?, val top1Pct: Double, val top5Pct: Double, val top10Pct: Double, val count: Int)

fun concentration(positions: List<Position>, total: Double): Concentration {
    val sorted = positions.sortedByDescending { it.cur }
    val share = { n: Int -> if (total > 0) sorted.take(n).sumOf { it.cur } / total * 100 else 0.0 }
    return Concentration(sorted.firstOrNull(), share(1), share(5), share(10), sorted.size)
}

data class Drawdown(val current: Double, val worst: Double, val days: Int)

/**
 * Drawdown of the market-only return, from the snapshots: each day's value change less the money added that day,
 * compounded, so money added does not read as a gain nor money withdrawn as a loss.
 */
fun drawdownOf(history: List<HistoryPoint>): Drawdown? {
    if (history.size < 8) return null
    var level = 1.0
    var peak = 1.0
    var worst = 0.0
    for (i in 1 until history.size) {
        val prev = history[i - 1]
        val cur = history[i]
        if (prev.value <= 0) continue
        level *= 1 + (cur.value - prev.value - (cur.invested - prev.invested)) / prev.value
        peak = maxOf(peak, level)
        worst = minOf(worst, level / peak - 1)
    }
    return Drawdown((level / peak - 1) * 100, worst * 100, history.size)
}

/** A class's weight against its target, and the rupees to add (positive) or trim (negative) at today's total. */
data class DriftRow(val cls: String, val weight: Double, val target: Double, val drift: Double, val move: Double)

fun driftRows(cards: List<ClassCard>, targets: Map<String, Double>, total: Double): List<DriftRow> =
    (cards.map { it.cls } + targets.filterValues { it > 0 }.keys).distinct().map { cls ->
        val c = cards.firstOrNull { it.cls == cls }
        val w = c?.weight ?: 0.0
        val t = targets[cls] ?: 0.0
        DriftRow(cls, w, t, w - t, t / 100 * total - (c?.cur ?: 0.0))
    }.sortedByDescending { kotlin.math.abs(it.move) }

// --- which holdings have no 1-day change, and why -------------------------------------------------------

data class DayCoverage(val reporting: Int, val total: Int, val missing: List<Position>, val reasons: List<String>)

private val NO_DAY_REASON = mapOf(
    "MUTUAL_FUND" to "Mutual funds publish one NAV a day. Their change is filled in from the published NAV history once the fund has an ISIN on file (press Sync after updating).",
    "US_STOCKS" to "INDmoney sent no day change for these US stocks.",
    "EQUITY" to "The broker sent no previous close for these stocks.",
    "GOLD" to "Gold bonds trade thinly, so no previous close is reported.",
    "NPS" to "NPS NAV is published once a day and the broker did not send a change.",
)

fun dayCoverage(positions: List<Position>): DayCoverage {
    val missing = positions.filter { it.day == null }
    return DayCoverage(
        positions.size - missing.size, positions.size, missing,
        missing.map { it.cls }.distinct().map { NO_DAY_REASON[it] ?: "The broker sent no day change for these." },
    )
}

/** The connections that need a login or are not working, for the notes and banners. */
fun needsAttention(s: BrokerSession) = s.status != "CONNECTED"

fun needsLogin(s: BrokerSession) = s.status == "AUTH_REQUIRED" || s.status == "SESSION_EXPIRED"

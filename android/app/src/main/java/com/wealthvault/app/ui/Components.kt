package com.wealthvault.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import java.math.BigDecimal
import java.math.RoundingMode
import kotlin.math.abs

// --- numbers, the web app's way: Indian grouping, true minus, a dash for unknown -------------------------

private const val MINUS = "−"
private const val DASH = "—"
private const val MASK = "₹ ••••"
/** joins a sign to its amount so a line never breaks between "+" and "₹3,794" */
private const val JOIN = "⁠"

/**
 * The "hide amounts" switch (the eye button, as on the web): while it is on every rupee amount reads ₹ ••••.
 * Percentages, weights and market prices of stocks are never hidden. Screens recompose when it flips.
 */
object Privacy {
    var hidden by mutableStateOf(true)
}

private fun masked(v: Double?) = v != null && !v.isNaN() && Privacy.hidden

private fun grouped(value: Double, digits: Int): String {
    val s = BigDecimal(value).setScale(digits, RoundingMode.HALF_UP).toPlainString()
    val whole = s.substringBefore('.')
    val frac = if (digits > 0) "." + s.substringAfter('.') else ""
    if (whole.length <= 3) return whole + frac
    val last3 = whole.takeLast(3)
    val rest = whole.dropLast(3).reversed().chunked(2).joinToString(",").reversed()
    return "$rest,$last3$frac"
}

private fun plainMoney(v: Double, digits: Int): String = (if (v < 0) MINUS else "") + "₹" + grouped(abs(v), digits)

/** ₹3,52,608 (hidden with the eye switch) */
fun money(v: Double?, digits: Int = 0): String = if (v == null || v.isNaN()) DASH else if (masked(v)) MASK else plainMoney(v, digits)

/** ₹2,938.40, a stock's market price: never hidden */
fun price(v: Double?): String = if (v == null || v.isNaN()) DASH else plainMoney(v, 2)

/** ₹2,938.40 for your own figures such as an average cost: hidden with the eye switch */
fun ownPrice(v: Double?): String = money(v, 2)

/** ₹70.41 L, ₹1.24 Cr; below a lakh, grouped rupees (hidden with the eye switch) */
fun compact(v: Double?): String {
    if (v == null || v.isNaN()) return DASH
    if (masked(v)) return MASK
    val a = abs(v)
    val sign = if (v < 0) MINUS else ""
    return when {
        a >= 1e7 -> sign + "₹" + String.format("%.2f Cr", a / 1e7)
        a >= 1e5 -> sign + "₹" + String.format("%.2f L", a / 1e5)
        else -> sign + "₹" + grouped(a, 0)
    }
}

/** +₹63,408 / −₹4,600 (hidden with the eye switch) */
fun signedMoney(v: Double?): String = if (v == null || v.isNaN()) DASH else if (masked(v)) MASK else (if (v < 0) MINUS else "+") + JOIN + plainMoney(abs(v), 0)

/** +₹1.24 L / −₹4,600 (hidden with the eye switch) */
fun signedCompact(v: Double?): String = if (v == null || v.isNaN()) DASH else if (masked(v)) MASK else (if (v < 0) MINUS else "+") + JOIN + compact(abs(v))

/** 6.23%: a share of the whole, never signed */
fun weightPct(v: Double?, digits: Int = 1): String = if (v == null || v.isNaN()) DASH else String.format("%.${digits}f%%", v)

/** +21.93% / −4.10% */
fun pct(v: Double?, digits: Int = 2): String {
    if (v == null || v.isNaN()) return DASH
    val s = String.format("%.${digits}f%%", abs(v))
    // a value that rounds to zero gets no sign ("0.0%", not "+0.0%" or "−0.0%")
    if (s.trimEnd('%').all { it == '0' || it == '.' }) return s
    return (if (v < 0) MINUS else "+") + JOIN + s
}

@Composable
fun toneOf(v: Double?): Color = when {
    v == null || v == 0.0 -> Wv.c.text
    v > 0 -> Wv.c.gain
    else -> Wv.c.loss
}

// --- building blocks ---------------------------------------------------------------------------------

/** The web app's card: surface, 1px border, 14px corners. */
@Composable
fun WvCard(modifier: Modifier = Modifier, padding: Int = 16, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(Wv.c.surface)
            .border(1.dp, Wv.c.border, RoundedCornerShape(14.dp))
            .padding(padding.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
        content = content,
    )
}

@Composable
fun Label(text: String) = Text(text.uppercase(), style = Wv.over, color = Wv.c.text3)

/** A KPI tile: label, a loud number, a quiet foot line. */
@Composable
fun Kpi(label: String, value: String, foot: String? = null, valueColor: Color = Wv.c.text, modifier: Modifier = Modifier) {
    WvCard(modifier) {
        Text(label, style = Wv.small, color = Wv.c.text3)
        Text(value, style = Wv.kpi, color = valueColor)
        if (foot != null) Text(foot, style = Wv.small, color = Wv.c.text3)
    }
}

enum class Tone { Ok, Warn, Bad, Off, Info }

@Composable
fun Badge(text: String, tone: Tone) {
    val (bg, fg) = when (tone) {
        Tone.Ok -> Wv.c.gainWeak to Wv.c.gain
        Tone.Warn -> Wv.c.warnWeak to Wv.c.warn
        Tone.Bad -> Wv.c.lossWeak to Wv.c.loss
        Tone.Info -> Wv.c.accentWeak to Wv.c.accent
        Tone.Off -> Wv.c.surface2 to Wv.c.text2
    }
    Text(
        text,
        style = Wv.small,
        color = fg,
        modifier = Modifier.clip(RoundedCornerShape(999.dp)).background(bg).padding(horizontal = 8.dp, vertical = 2.dp),
    )
}

/** A note strip: grey for information, red for a problem. */
@Composable
fun Note(text: String, bad: Boolean = false) {
    Text(
        text,
        style = Wv.sub,
        color = if (bad) Wv.c.loss else Wv.c.text2,
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(if (bad) Wv.c.lossWeak else Wv.c.surface2)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    )
}

/** One stacked bar of the asset mix, each class in its fixed colour (always shown with a labelled legend). */
@Composable
fun MixBar(parts: List<Pair<Color, Double>>) {
    Row(
        Modifier.fillMaxWidth().height(10.dp).clip(RoundedCornerShape(5.dp)).background(Wv.c.surface2),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        parts.filter { it.second > 0 }.forEach { (color, weight) ->
            Box(Modifier.weight(weight.toFloat()).height(10.dp).background(color))
        }
    }
}

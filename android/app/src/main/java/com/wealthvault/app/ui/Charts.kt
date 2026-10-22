package com.wealthvault.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** One line on a chart. Values line up with the chart's dates; null leaves a gap. [step] draws a level (a stop, a high) as steps. */
data class Series(val label: String, val color: Color, val values: List<Double?>, val dashed: Boolean = false, val step: Boolean = false, val thin: Boolean = false)

/** A buy (triangle up), a sell (triangle down) or a stop exit (cross) on day [index], drawn at [value]. */
data class ChartMarker(val index: Int, val value: Double, val kind: Kind, val color: Color) {
    enum class Kind { Up, Down, Cross }
}

/**
 * A plain line chart in the web app's style: 2px lines, a recessive grid, one value axis, a legend whenever there
 * is more than one line, and a press-and-drag readout of every line on that day (text in text colours, never the
 * line colour).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun LineChart(
    dates: List<String>,
    series: List<Series>,
    format: (Double) -> String,
    modifier: Modifier = Modifier,
    height: Dp = 200.dp,
    markers: List<ChartMarker> = emptyList(),
    /** day ranges shaded behind the lines (a bullish regime, a setup window), labelled in the legend by [bandLabel] */
    bands: List<IntRange> = emptyList(),
    bandColor: Color = Color.Unspecified,
    bandLabel: String? = null,
) {
    if (dates.size < 2 || series.isEmpty()) return
    // a phone is ~400 px wide: keep every k-th day (and the last) so long backtests draw quickly; marks and bands
    // move to the nearest kept day
    if (dates.size > 500) {
        val step = (dates.size + 399) / 400
        val keep = dates.indices.filter { it % step == 0 || it == dates.lastIndex }
        val near = { i: Int -> keep.indexOfFirst { it >= i }.let { if (it < 0) keep.lastIndex else it } }
        return LineChart(
            keep.map { dates[it] }, series.map { s -> s.copy(values = keep.map { s.values.getOrNull(it) }) }, format, modifier, height,
            markers.map { it.copy(index = near(it.index)) }, bands.map { near(it.first)..near(it.last) }, bandColor, bandLabel,
        )
    }
    val all = series.flatMap { s -> s.values.filterNotNull() }
    if (all.isEmpty()) return
    var lo = all.min()
    var hi = all.max()
    if (hi == lo) { hi += 1; lo -= 1 }
    val pad = (hi - lo) * 0.06
    lo -= pad; hi += pad
    val grid = Wv.c.border
    val cross = Wv.c.text3
    val surface = Wv.c.surface
    var touch by remember(dates) { mutableStateOf<Int?>(null) }

    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (series.size > 1 || bandLabel != null) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                series.forEach { s ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.width(14.dp).height(3.dp).clip(RoundedCornerShape(2.dp)).background(s.color))
                        Spacer(Modifier.width(6.dp))
                        Text(s.label, style = Wv.small, color = Wv.c.text2)
                    }
                }
                if (bandLabel != null && bands.isNotEmpty()) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.width(14.dp).height(10.dp).clip(RoundedCornerShape(2.dp)).background(bandColor.copy(alpha = 0.18f)))
                        Spacer(Modifier.width(6.dp))
                        Text(bandLabel, style = Wv.small, color = Wv.c.text2)
                    }
                }
            }
        }
        // the readout for the touched day, or the latest day
        val i = touch ?: (dates.size - 1)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(longDate(dates[i]), style = Wv.small.copy(fontWeight = FontWeight.SemiBold), color = Wv.c.text)
            series.forEach { s ->
                s.values.getOrNull(i)?.let { v ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(7.dp).clip(RoundedCornerShape(4.dp)).background(s.color))
                        Spacer(Modifier.width(4.dp))
                        Text(format(v), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text2)
                    }
                }
            }
        }
        Row {
            Canvas(
                Modifier
                    .weight(1f)
                    .height(height)
                    // a press or a sideways drag reads the chart; an up-down swipe is left to the page so it scrolls
                    .pointerInput(dates) {
                        val pick = { x: Float -> ((x / size.width) * (dates.size - 1)).toInt().coerceIn(0, dates.size - 1) }
                        detectTapGestures(onPress = { o -> touch = pick(o.x); tryAwaitRelease(); touch = null })
                    }
                    .pointerInput(dates) {
                        val pick = { x: Float -> ((x / size.width) * (dates.size - 1)).toInt().coerceIn(0, dates.size - 1) }
                        detectHorizontalDragGestures(
                            onDragStart = { o -> touch = pick(o.x) },
                            onDragEnd = { touch = null },
                            onDragCancel = { touch = null },
                        ) { change, _ -> touch = pick(change.position.x); change.consume() }
                    },
            ) {
                val w = size.width
                val h = size.height
                val x = { k: Int -> w * k / (dates.size - 1) }
                val y = { v: Double -> (h * (1 - (v - lo) / (hi - lo))).toFloat() }
                bands.forEach { b ->
                    drawRect(bandColor.copy(alpha = 0.08f), topLeft = Offset(x(b.first), 0f), size = androidx.compose.ui.geometry.Size((x(b.last) - x(b.first)).coerceAtLeast(1f), h))
                }
                for (g in 0..3) {
                    val gy = h * g / 3
                    drawLine(grid, Offset(0f, gy), Offset(w, gy), strokeWidth = 1f)
                }
                series.forEach { s ->
                    val path = Path()
                    var started = false
                    var prevY = 0f
                    s.values.forEachIndexed { k, v ->
                        if (v == null) { started = false; return@forEachIndexed }
                        when {
                            !started -> { path.moveTo(x(k), y(v)); started = true }
                            s.step -> { path.lineTo(x(k), prevY); path.lineTo(x(k), y(v)) }
                            else -> path.lineTo(x(k), y(v))
                        }
                        prevY = y(v)
                    }
                    drawPath(
                        path, s.color,
                        style = Stroke(width = (if (s.thin) 1.5 else 2.0).dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round, pathEffect = if (s.dashed) PathEffect.dashPathEffect(floatArrayOf(12f, 8f)) else null),
                    )
                }
                val m = 6.dp.toPx()
                markers.forEach { mk ->
                    val cx = x(mk.index)
                    val cy = y(mk.value)
                    when (mk.kind) {
                        ChartMarker.Kind.Up -> drawPath(Path().apply { moveTo(cx, cy - m); lineTo(cx - m, cy + m); lineTo(cx + m, cy + m); close() }, mk.color)
                        ChartMarker.Kind.Down -> drawPath(Path().apply { moveTo(cx, cy + m); lineTo(cx - m, cy - m); lineTo(cx + m, cy - m); close() }, mk.color)
                        ChartMarker.Kind.Cross -> {
                            drawLine(mk.color, Offset(cx - m, cy - m), Offset(cx + m, cy + m), strokeWidth = 2.dp.toPx())
                            drawLine(mk.color, Offset(cx - m, cy + m), Offset(cx + m, cy - m), strokeWidth = 2.dp.toPx())
                        }
                    }
                }
                touch?.let { t ->
                    drawLine(cross, Offset(x(t), 0f), Offset(x(t), h), strokeWidth = 1f)
                    series.forEach { s ->
                        s.values.getOrNull(t)?.let { v ->
                            drawCircle(surface, radius = 6.dp.toPx(), center = Offset(x(t), y(v)))
                            drawCircle(s.color, radius = 4.dp.toPx(), center = Offset(x(t), y(v)))
                        }
                    }
                }
            }
            Column(Modifier.height(height).padding(start = 6.dp), verticalArrangement = Arrangement.SpaceBetween) {
                Text(format(hi - pad), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
                Text(format(lo + pad), style = Wv.small.copy(fontFeatureSettings = "tnum"), color = Wv.c.text3)
            }
        }
        Row {
            Text(shortDate(dates.first()) + " " + dates.first().take(4), style = Wv.small, color = Wv.c.text3, modifier = Modifier.weight(1f))
            Text(shortDate(dates.last()) + " " + dates.last().take(4), style = Wv.small, color = Wv.c.text3)
        }
    }
}

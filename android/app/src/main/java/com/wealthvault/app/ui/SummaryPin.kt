package com.wealthvault.app.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * True once the list has been scrolled past the item with [key] (it is no longer on screen and the list is not at
 * the top). Drives the pinned summary bar, as the web's SummaryPin does (web/src/components/SummaryPin.tsx).
 */
@Composable
fun pastItem(state: LazyListState, key: String): State<Boolean> =
    remember(state, key) {
        derivedStateOf { state.firstVisibleItemIndex > 0 && state.layoutInfo.visibleItemsInfo.none { it.key == key } }
    }

/** Invested, Current, Total P&L and Day P&L on one slim line, pinned over the list once the full cards scroll away. */
@Composable
fun SummaryPinBar(visible: Boolean, totals: Totals, onClick: () -> Unit, below: @Composable () -> Unit = {}) {
    AnimatedVisibility(visible, enter = slideInVertically { -it } + fadeIn(), exit = slideOutVertically { -it } + fadeOut()) {
        Column(Modifier.fillMaxWidth().background(Wv.c.bg).padding(horizontal = 16.dp).padding(bottom = 6.dp)) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(0.dp, 0.dp, 12.dp, 12.dp))
                    .background(Wv.c.surface)
                    .border(1.dp, Wv.c.border, RoundedCornerShape(0.dp, 0.dp, 12.dp, 12.dp))
                    .clickable(onClickLabel = "Back to the summary", onClick = onClick)
                    .semantics { contentDescription = "Portfolio summary. Tap to go back to the top" }
                    .padding(horizontal = 12.dp, vertical = 8.dp),
            ) {
                PinCell("INVESTED", compact(totals.inv), null, null, Modifier.weight(1f))
                PinCell("CURRENT", compact(totals.cur), null, null, Modifier.weight(1f))
                PinCell("TOTAL P&L", signedCompact(totals.pnl), pct(totals.pnlPct, 1), toneOf(totals.pnl), Modifier.weight(1f))
                PinCell("DAY P&L", if (totals.day == null) "—" else signedCompact(totals.day), totals.day?.let { pct(totals.dayPct, 1) }, toneOf(totals.day), Modifier.weight(1f))
            }
            below()
        }
    }
}

@Composable
private fun PinCell(label: String, value: String, sub: String?, tone: androidx.compose.ui.graphics.Color?, modifier: Modifier) {
    Column(modifier) {
        Text(label, style = Wv.small.copy(fontSize = 9.sp, letterSpacing = 0.4.sp, fontWeight = FontWeight.SemiBold), color = Wv.c.text3, maxLines = 1)
        Text(value, style = Wv.small.copy(fontSize = 13.sp, fontWeight = FontWeight.SemiBold, fontFeatureSettings = "tnum"), color = tone ?: Wv.c.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(sub ?: " ", style = Wv.small.copy(fontSize = 10.sp, fontFeatureSettings = "tnum"), color = tone ?: Wv.c.text3, maxLines = 1)
    }
}

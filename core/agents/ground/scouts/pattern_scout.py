"""Pattern Finder Scout: Classical Chart Geometry Detection.

Scans historical daily OHLCV candles to detect high-probability institutional chart geometries:
1. Ascending Triangle (Flat resistance ceiling + ascending swing lows + volume contraction)
2. Volatility Contraction Pattern (VCP / Mark Minervini - successive tightening wave depths)
3. Cup and Handle (Rounded base accumulation + tight handle pullback)
4. Double Bottom (W-formation with support confirmation)
5. Head & Shoulders / Double Top (Distribution / breakdown warnings)

Returns pattern_detected=False if the stock is merely consolidating without distinct geometry.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy.signal import argrelextrema

from core.agents.forensic_crawler import clean_symbol
from core.agents.ground.contracts import PatternIntelReport

logger = logging.getLogger("wealthvault.agents.ground.pattern_scout")


def _evaluate_volume_signature(
    volumes: np.ndarray,
    is_near_pivot: bool,
    is_breakout: bool,
) -> Tuple[Optional[float], Optional[bool], bool, int, str]:
    """
    Evaluates:
    - volume_surge_ratio: Breakout candle volume vs 20-DMA (e.g. 1.8x)
    - volume_dryup_confirmed: True if volume dried up during consolidation (< 0.80x 20-DMA)
    - is_low_volume_trap: True if breaking out on < 1.0x 20-DMA (Retail Bull Trap)
    - conf_delta: Adjustment to confidence (-35 for bull trap, +10 for verified surge)
    - vol_note: Diagnostic summary note
    """
    if len(volumes) < 20:
        return None, None, False, 0, ""

    vol_sma_20 = float(np.mean(volumes[-21:-1])) if len(volumes) >= 21 else float(np.mean(volumes))
    cur_vol = float(volumes[-1])
    vol_surge_ratio = round(cur_vol / vol_sma_20, 2) if vol_sma_20 > 0 else 1.0

    # Dry-up check in base (last 5 sessions before today)
    base_vol = float(np.mean(volumes[-6:-1])) if len(volumes) >= 6 else cur_vol
    volume_dryup_confirmed = base_vol < 0.85 * vol_sma_20 if vol_sma_20 > 0 else False

    is_low_volume_trap = False
    conf_delta = 0
    vol_note = ""

    if is_breakout:
        if vol_surge_ratio >= 1.50:
            is_low_volume_trap = False
            conf_delta = +10
            vol_note = f"Verified institutional volume surge ({vol_surge_ratio:.1f}x 20-DMA)."
        elif vol_surge_ratio < 1.00:
            is_low_volume_trap = True
            conf_delta = -35
            vol_note = f"⚠️ Low-volume breakout ({vol_surge_ratio:.1f}x 20-DMA) — Potential Retail Bull Trap!"
        else:
            is_low_volume_trap = False
            conf_delta = 0
            vol_note = f"Moderate breakout volume ({vol_surge_ratio:.1f}x 20-DMA)."
    elif is_near_pivot:
        if volume_dryup_confirmed:
            conf_delta = +5
            vol_note = f"Supply drying up in base ({vol_surge_ratio:.1f}x 20-DMA). Ready for volume surge."
        else:
            conf_delta = 0
            vol_note = f"Consolidation volume at {vol_surge_ratio:.1f}x 20-DMA."
    else:
        vol_note = f"Volume: {vol_surge_ratio:.1f}x 20-DMA."

    return vol_surge_ratio, volume_dryup_confirmed, is_low_volume_trap, conf_delta, vol_note


class PatternScout:
    """Scout for geometric chart patterns and breakout pivots."""

    def evaluate(self, symbol: str, candles: List[Dict[str, Any]]) -> PatternIntelReport:
        clean = clean_symbol(symbol)
        if not candles or len(candles) < 30:
            return PatternIntelReport(
                symbol=clean,
                pattern_detected=False,
                summary="Insufficient historical candles (< 30 sessions) for pattern geometry recognition.",
            )

        try:
            # Extract price and volume arrays (most recent 120 candles)
            subset = candles[-120:]
            closes = np.array([float(c["close"]) for c in subset])
            highs = np.array([float(c["high"]) for c in subset])
            lows = np.array([float(c["low"]) for c in subset])
            volumes = np.array([float(c.get("volume", 0) or 0) for c in subset])
            cur_price = closes[-1]

            # Find local extrema (window of 3 days on each side)
            order = 3
            peak_indices = argrelextrema(highs, np.greater, order=order)[0]
            trough_indices = argrelextrema(lows, np.less, order=order)[0]

            # 1. Check for Ascending Triangle
            tri = self._check_ascending_triangle(subset, highs, lows, closes, volumes, peak_indices, trough_indices, cur_price)
            if tri:
                return tri

            # 2. Check for Volatility Contraction Pattern (VCP)
            vcp = self._check_vcp(subset, highs, lows, closes, volumes, peak_indices, trough_indices, cur_price)
            if vcp:
                return vcp

            # 3. Check for Cup and Handle
            cup = self._check_cup_and_handle(subset, highs, lows, closes, volumes, cur_price)
            if cup:
                return cup

            # 4. Check for Double Bottom (W-formation)
            db = self._check_double_bottom(subset, highs, lows, closes, volumes, trough_indices, cur_price)
            if db:
                return db

            # 5. Check for Head & Shoulders Breakdown Warning
            hs = self._check_head_and_shoulders(subset, highs, lows, closes, peak_indices, cur_price)
            if hs:
                return hs

            # No distinct geometry confirmed
            return PatternIntelReport(
                symbol=clean,
                pattern_detected=False,
                bias="NEUTRAL",
                summary="No distinct classical chart pattern formed. Price is in normal trend or wide consolidation.",
            )
        except Exception as exc:
            logger.warning("PatternScout evaluation error for %s: %s", clean, exc)
            return PatternIntelReport(
                symbol=clean,
                pattern_detected=False,
                status="FAILED",
                summary=f"Pattern analysis calculation error: {str(exc)}",
            )

    def _check_ascending_triangle(
        self,
        candles: List[Dict[str, Any]],
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray,
        peaks: np.ndarray,
        troughs: np.ndarray,
        cur_price: float,
    ) -> Optional[PatternIntelReport]:
        """Ascending Triangle: Flat horizontal resistance + ascending swing lows."""
        if len(peaks) < 2 or len(troughs) < 2:
            return None

        # Look at the last 2-3 peaks and troughs
        recent_peaks = peaks[-3:] if len(peaks) >= 3 else peaks[-2:]
        recent_troughs = troughs[-3:] if len(troughs) >= 3 else troughs[-2:]

        peak_vals = highs[recent_peaks]
        trough_vals = lows[recent_troughs]

        # Horizontal resistance check: peaks within 2.5% of each other
        resistance = float(np.mean(peak_vals))
        peak_dispersion = (np.max(peak_vals) - np.min(peak_vals)) / resistance
        if peak_dispersion > 0.025:
            return None

        # Ascending support check: each successive trough must be higher
        ascending_lows = all(trough_vals[i] > trough_vals[i - 1] * 1.008 for i in range(1, len(trough_vals)))
        if not ascending_lows:
            return None

        # Volume check: volume during the formation should contract towards apex
        vol_contraction = False
        if len(volumes) >= 20:
            first_half_vol = np.mean(volumes[-40:-20]) if len(volumes) >= 40 else np.mean(volumes[:len(volumes)//2])
            second_half_vol = np.mean(volumes[-20:])
            vol_contraction = second_half_vol <= first_half_vol * 1.1

        latest_low = float(trough_vals[-1])
        pct_to_resistance = ((resistance - cur_price) / resistance) * 100.0

        is_breakout = cur_price >= resistance * 1.005
        is_near = abs(pct_to_resistance) <= 2.5

        if is_breakout:
            stage = "CONFIRMED_BREAKOUT"
            conf = 85 if vol_contraction else 75
        elif is_near:
            stage = "NEAR_PIVOT"
            conf = 80 if vol_contraction else 70
        else:
            stage = "FORMING"
            conf = 65

        vol_surge, vol_dryup, is_trap, conf_delta, vol_note = _evaluate_volume_signature(
            volumes, is_near, is_breakout
        )
        conf = max(10, min(95, conf + conf_delta))

        summary = (
            f"Ascending Triangle forming with horizontal ceiling at ₹{resistance:.1f} and higher swing lows "
            f"(latest support at ₹{latest_low:.1f}). Price is {pct_to_resistance:+.1f}% from breakout pivot."
        )
        if vol_note:
            summary = f"{summary} {vol_note}"

        return PatternIntelReport(
            symbol=candles[-1].get("symbol", ""),
            pattern_detected=True,
            pattern_name="Ascending Triangle",
            bias="BULLISH",
            confidence=conf,
            pivot_breakout_price=round(resistance, 2),
            support_stop_price=round(latest_low, 2),
            pattern_stage=stage,
            volume_surge_ratio=vol_surge,
            volume_dryup_confirmed=vol_dryup,
            is_low_volume_trap=is_trap,
            summary=summary,
        )

    def _check_vcp(
        self,
        candles: List[Dict[str, Any]],
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray,
        peaks: np.ndarray,
        troughs: np.ndarray,
        cur_price: float,
    ) -> Optional[PatternIntelReport]:
        """Volatility Contraction Pattern (VCP): Progressive tightening of pullback depths."""
        if len(peaks) < 2 or len(troughs) < 2:
            return None

        # Measure wave depths between peaks and succeeding troughs
        contractions = []
        for i in range(len(peaks) - 1):
            p_idx = peaks[i]
            # Find trough between this peak and next peak
            valid_troughs = [t for t in troughs if p_idx < t < peaks[i + 1]]
            if valid_troughs:
                p_val = highs[p_idx]
                t_val = min(lows[valid_troughs])
                depth = (p_val - t_val) / p_val
                contractions.append(depth)

        if len(contractions) < 2:
            return None

        # Check if contractions are progressively tightening (e.g. 18% -> 8% -> 3%)
        is_tightening = all(contractions[j] < contractions[j - 1] * 0.85 for j in range(1, len(contractions)))
        if not is_tightening:
            return None

        pivot = float(max(highs[peaks[-2:]]))
        stop = float(lows[troughs[-1]])
        last_contraction_pct = contractions[-1] * 100.0

        is_breakout = cur_price >= pivot * 1.005
        is_near = cur_price >= pivot * 0.98

        if is_breakout:
            stage = "CONFIRMED_BREAKOUT"
            conf = 85
        elif is_near:
            stage = "NEAR_PIVOT"
            conf = 80
        else:
            stage = "FORMING"
            conf = 70

        vol_surge, vol_dryup, is_trap, conf_delta, vol_note = _evaluate_volume_signature(
            volumes, is_near, is_breakout
        )
        conf = max(10, min(95, conf + conf_delta))

        summary = (
            f"VCP detected: {len(contractions)} successive contractions with final wave tightening to "
            f"{last_contraction_pct:.1f}%. Pivot at ₹{pivot:.1f}, structural stop at ₹{stop:.1f}."
        )
        if vol_note:
            summary = f"{summary} {vol_note}"

        return PatternIntelReport(
            symbol=candles[-1].get("symbol", ""),
            pattern_detected=True,
            pattern_name="Volatility Contraction (VCP)",
            bias="BULLISH",
            confidence=conf,
            pivot_breakout_price=round(pivot, 2),
            support_stop_price=round(stop, 2),
            pattern_stage=stage,
            volume_surge_ratio=vol_surge,
            volume_dryup_confirmed=vol_dryup,
            is_low_volume_trap=is_trap,
            summary=summary,
        )

    def _check_cup_and_handle(
        self,
        candles: List[Dict[str, Any]],
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray,
        cur_price: float,
    ) -> Optional[PatternIntelReport]:
        """Cup and Handle: Rounded base (30-90 days) followed by shallow handle (5-15 days)."""
        if len(closes) < 45:
            return None

        # Cup region (last 45 to 15 days) and handle (last 15 days)
        cup_highs = highs[-60:-15] if len(highs) >= 60 else highs[:-15]
        cup_lows = lows[-60:-15] if len(lows) >= 60 else lows[:-15]
        handle_highs = highs[-15:]
        handle_lows = lows[-15:]

        left_rim = float(np.max(cup_highs[:len(cup_highs)//3]))
        cup_bottom = float(np.min(cup_lows))
        right_rim = float(np.max(cup_highs[2*len(cup_highs)//3:]))

        # Lip symmetry: left rim and right rim within 5%
        if abs(left_rim - right_rim) / left_rim > 0.05:
            return None

        # Depth check: Cup depth between 10% and 35%
        cup_depth = (right_rim - cup_bottom) / right_rim
        if cup_depth < 0.10 or cup_depth > 0.35:
            return None

        # Handle check: Handle pullback should be shallow (3% to 12% below right rim)
        handle_bottom = float(np.min(handle_lows))
        handle_depth = (right_rim - handle_bottom) / right_rim
        if handle_depth < 0.02 or handle_depth > 0.14:
            return None

        pivot = round(right_rim, 2)
        stop = round(handle_bottom, 2)
        pct_to_pivot = ((pivot - cur_price) / pivot) * 100.0

        is_breakout = cur_price >= pivot * 1.005
        is_near = abs(pct_to_pivot) <= 3.0

        if is_breakout:
            stage = "CONFIRMED_BREAKOUT"
            conf = 85
        elif is_near:
            stage = "NEAR_PIVOT"
            conf = 80
        else:
            stage = "FORMING"
            conf = 70

        vol_surge, vol_dryup, is_trap, conf_delta, vol_note = _evaluate_volume_signature(
            volumes, is_near, is_breakout
        )
        conf = max(10, min(95, conf + conf_delta))

        summary = (
            f"Cup & Handle formation: {cup_depth*100:.1f}% rounded base with a tight {handle_depth*100:.1f}% handle. "
            f"Breakout pivot at ₹{pivot:.1f}, handle support at ₹{stop:.1f}."
        )
        if vol_note:
            summary = f"{summary} {vol_note}"

        return PatternIntelReport(
            symbol=candles[-1].get("symbol", ""),
            pattern_detected=True,
            pattern_name="Cup and Handle",
            bias="BULLISH",
            confidence=conf,
            pivot_breakout_price=pivot,
            support_stop_price=stop,
            pattern_stage=stage,
            volume_surge_ratio=vol_surge,
            volume_dryup_confirmed=vol_dryup,
            is_low_volume_trap=is_trap,
            summary=summary,
        )

    def _check_double_bottom(
        self,
        candles: List[Dict[str, Any]],
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray,
        troughs: np.ndarray,
        cur_price: float,
    ) -> Optional[PatternIntelReport]:
        """Double Bottom (W-formation): Two swing lows with an intervening neckline."""
        if len(troughs) < 2:
            return None

        t1_idx = troughs[-2]
        t2_idx = troughs[-1]

        # Separation: between 8 and 50 trading days
        if (t2_idx - t1_idx) < 8 or (t2_idx - t1_idx) > 50:
            return None

        l1 = float(lows[t1_idx])
        l2 = float(lows[t2_idx])

        # Bottom level equality: within 3%
        if abs(l1 - l2) / l1 > 0.03:
            return None

        # Intervening peak (neckline)
        between_highs = highs[t1_idx:t2_idx]
        if len(between_highs) == 0:
            return None
        neckline = float(np.max(between_highs))

        # Height check: Neckline must be at least 5% above the bottoms
        if (neckline - min(l1, l2)) / min(l1, l2) < 0.05:
            return None

        pivot = round(neckline, 2)
        stop = round(min(l1, l2), 2)

        is_breakout = cur_price >= neckline * 1.005
        is_near = cur_price >= neckline * 0.97

        if is_breakout:
            stage = "CONFIRMED_BREAKOUT"
            conf = 80
        elif is_near:
            stage = "NEAR_PIVOT"
            conf = 75
        else:
            stage = "FORMING"
            conf = 65

        vol_surge, vol_dryup, is_trap, conf_delta, vol_note = _evaluate_volume_signature(
            volumes, is_near, is_breakout
        )
        conf = max(10, min(95, conf + conf_delta))

        summary = (
            f"Double Bottom (W-Pattern): Twin support confirmed at ₹{stop:.1f}. "
            f"Neckline breakout level at ₹{pivot:.1f}."
        )
        if vol_note:
            summary = f"{summary} {vol_note}"

        return PatternIntelReport(
            symbol=candles[-1].get("symbol", ""),
            pattern_detected=True,
            pattern_name="Double Bottom",
            bias="BULLISH",
            confidence=conf,
            pivot_breakout_price=pivot,
            support_stop_price=stop,
            pattern_stage=stage,
            volume_surge_ratio=vol_surge,
            volume_dryup_confirmed=vol_dryup,
            is_low_volume_trap=is_trap,
            summary=summary,
        )

    def _check_head_and_shoulders(
        self,
        candles: List[Dict[str, Any]],
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        peaks: np.ndarray,
        cur_price: float,
    ) -> Optional[PatternIntelReport]:
        """Head and Shoulders (Distribution warning): Left shoulder, higher Head, lower Right shoulder."""
        if len(peaks) < 3:
            return None

        p1, p2, p3 = peaks[-3], peaks[-2], peaks[-1]
        h1, h2, h3 = float(highs[p1]), float(highs[p2]), float(highs[p3])

        # Head must be higher than both shoulders
        if not (h2 > h1 * 1.02 and h2 > h3 * 1.02):
            return None

        # Shoulders should be roughly comparable (within 5%)
        if abs(h1 - h3) / h1 > 0.06:
            return None

        # Neckline is the minimum trough between the shoulders
        neckline = float(np.min(lows[p1:p3]))

        if cur_price <= neckline * 1.01:
            stage = "CONFIRMED_BREAKDOWN" if cur_price < neckline else "NEAR_BREAKDOWN"
            conf = 85
        else:
            stage = "FORMING"
            conf = 65

        summary = (
            f"Head & Shoulders Distribution pattern: Head at ₹{h2:.1f}, shoulders at ₹{h1:.1f}/₹{h3:.1f}. "
            f"Critical breakdown neckline at ₹{neckline:.1f}."
        )

        return PatternIntelReport(
            symbol=candles[-1].get("symbol", ""),
            pattern_detected=True,
            pattern_name="Head and Shoulders",
            bias="BEARISH",
            confidence=conf,
            pivot_breakout_price=None,
            support_stop_price=round(neckline, 2),
            pattern_stage=stage,
            summary=summary,
        )

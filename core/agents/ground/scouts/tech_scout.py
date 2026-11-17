"""Technical Momentum Scout: Moving Averages, Stage Analysis & Relative Strength.

Evaluates stored historical OHLCV candles to determine:
- 50-DMA and 200-DMA alignment
- 200-DMA slope %
- Golden / Death Cross state
- Weinstein Stage classification (Stage 1 Accumulation, Stage 2 Markup, Stage 3 Distribution, Stage 4 Capitulation)
- Relative Strength vs NIFTY 50
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from core.agents.forensic_crawler import clean_symbol
from core.agents.ground.contracts import TechIntelReport
from core.analytics import analyze_momentum

logger = logging.getLogger("wealthvault.agents.ground.tech_scout")


def _classify_market_regime(
    benchmark_candles: Optional[List[Dict[str, Any]]],
) -> Tuple[Optional[str], Optional[str]]:
    """Determine Nifty 50 macro market regime and summary."""
    if not benchmark_candles or len(benchmark_candles) < 30:
        return None, None

    try:
        closes = [float(c["close"]) for c in benchmark_candles]
        cur_nifty = closes[-1]

        # 50-DMA
        sma_50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else float(np.mean(closes))
        # 200-DMA if available
        sma_200 = float(np.mean(closes[-200:])) if len(closes) >= 200 else None

        if sma_200 is not None:
            if cur_nifty >= sma_50 and (cur_nifty >= sma_200 or sma_50 >= sma_200):
                regime = "BULL_MARKET"
                summary = f"NIFTY 50 (₹{cur_nifty:.0f}) above 50-DMA (₹{sma_50:.0f}) & 200-DMA (₹{sma_200:.0f}) — Risk-On Regime"
            elif cur_nifty < sma_50 and cur_nifty < sma_200:
                regime = "BEAR_CORRECTION"
                summary = f"NIFTY 50 (₹{cur_nifty:.0f}) below 50-DMA (₹{sma_50:.0f}) & 200-DMA (₹{sma_200:.0f}) — Defensive Regime"
            else:
                regime = "NEUTRAL_CHOPPY"
                summary = f"NIFTY 50 (₹{cur_nifty:.0f}) consolidating between 50-DMA (₹{sma_50:.0f}) & 200-DMA (₹{sma_200:.0f})"
        else:
            if cur_nifty >= sma_50:
                regime = "BULL_MARKET"
                summary = f"NIFTY 50 (₹{cur_nifty:.0f}) above 50-DMA (₹{sma_50:.0f}) — Risk-On Regime"
            else:
                regime = "BEAR_CORRECTION"
                summary = f"NIFTY 50 (₹{cur_nifty:.0f}) below 50-DMA (₹{sma_50:.0f}) — Defensive Regime"

        return regime, summary
    except Exception as exc:
        logger.warning("Error classifying market regime: %s", exc)
        return None, None


class TechScout:
    """Scout for moving averages, Stage analysis, and momentum."""

    def evaluate(
        self,
        symbol: str,
        candles: List[Dict[str, Any]],
        benchmark_candles: Optional[List[Dict[str, Any]]] = None,
    ) -> TechIntelReport:
        clean = clean_symbol(symbol)
        if not candles or len(candles) < 20:
            return TechIntelReport(
                symbol=clean,
                status="FAILED",
                summary="Insufficient historical candles (< 20 sessions) to evaluate moving averages.",
            )

        try:
            analysis = analyze_momentum(f"NSE:{clean}", candles, benchmark_candles=benchmark_candles)

            # Map trend verdict to Stan Weinstein stage
            score = analysis.trend_score
            slope = analysis.sma200_slope_pct or 0.0
            cur_price = analysis.last_price or (candles[-1]["close"] if candles else 0.0)
            sma_50 = analysis.sma_50
            sma_200 = analysis.sma_200

            if score >= 4:
                stage = "Stage 2: Markup (Strong Bullish)"
            elif score == 3:
                stage = "Stage 2: Early Bullish / Breakout"
            elif score == 2:
                stage = "Stage 1: Base / Consolidation"
            elif score == 1:
                stage = "Stage 3: Distribution / Top Building"
            else:
                stage = "Stage 4: Capitulation / Downtrend"

            is_golden = None
            if sma_50 is not None and sma_200 is not None:
                is_golden = sma_50 > sma_200

            # Compute relative strength vs Nifty
            rs_score = None
            rs_rating_label = None
            if isinstance(analysis.relative_strength, dict):
                rs_score = analysis.relative_strength.get("3M")
                if rs_score is None:
                    rs_score = analysis.relative_strength.get("6M")
                if rs_score is None:
                    rs_score = analysis.relative_strength.get("1M")

            if rs_score is not None:
                if rs_score >= 5.0:
                    rs_rating_label = "OUTPERFORMING"
                elif rs_score <= -5.0:
                    rs_rating_label = "UNDERPERFORMING"
                else:
                    rs_rating_label = "IN_LINE"

            # Macro Market Regime from benchmark candles
            market_regime, nifty_summary = _classify_market_regime(benchmark_candles)

            summary_parts = [
                f"{analysis.trend_verdict} ({score}/{analysis.trend_max_score})",
                stage,
            ]
            if sma_50 and sma_200:
                summary_parts.append(f"50-DMA: ₹{sma_50:.1f} | 200-DMA: ₹{sma_200:.1f} (Slope: {slope:+.1f}%)")
            if rs_score is not None and rs_rating_label:
                summary_parts.append(f"RS vs Nifty: {rs_score:+.1f}% ({rs_rating_label})")
            if market_regime:
                summary_parts.append(f"Regime: {market_regime}")

            return TechIntelReport(
                symbol=clean,
                current_price=cur_price,
                sma_50=round(sma_50, 2) if sma_50 is not None else None,
                sma_200=round(sma_200, 2) if sma_200 is not None else None,
                slope_200_sma=round(slope, 2),
                golden_cross=is_golden,
                stage_verdict=stage,
                momentum_score=score,
                momentum_max=analysis.trend_max_score,
                rs_score_vs_nifty=round(rs_score, 2) if rs_score is not None else None,
                rs_rating_label=rs_rating_label,
                market_regime=market_regime,
                nifty_trend_summary=nifty_summary,
                status="COMPLETED",
                summary=" | ".join(summary_parts),
            )
        except Exception as exc:
            logger.warning("TechScout evaluation error for %s: %s", clean, exc)
            return TechIntelReport(
                symbol=clean,
                status="FAILED",
                summary=f"Technical analysis error: {str(exc)}",
            )

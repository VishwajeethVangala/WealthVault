"""Candle Delta Sync & Local Storage Cache for Ground Scouts.

Downstream scouts (Technical Scout, Pattern Scout) query this module to read historical
daily OHLCV candles. It ensures candles are stored locally and only topped up incrementally,
protecting broker endpoints from redundant traffic.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from core.agents.forensic_crawler import clean_symbol

logger = logging.getLogger("wealthvault.agents.ground.candle_sync")

# In-process candle memory cache: symbol -> (instrument, candles, benchmark_candles)
_CANDLE_MEM_CACHE: Dict[str, Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], Optional[List[Dict[str, Any]]]]] = {}


async def get_or_sync_candles(
    symbol: str,
    owner_id: Optional[str] = None,
    lookback_days: int = 400,
    force_refresh: bool = False,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    """Retrieve historical daily candles for a stock, topping up incremental deltas if needed."""
    clean = clean_symbol(symbol)
    
    if not force_refresh and clean in _CANDLE_MEM_CACHE:
        return _CANDLE_MEM_CACHE[clean]

    try:
        from apps.api.routers.analytics import _load_candles
        inst, candles, bm = await _load_candles(
            owner_id=owner_id,
            symbol=clean,
            lookback_days=lookback_days,
            with_benchmark=True,
        )
        if candles:
            _CANDLE_MEM_CACHE[clean] = (inst, candles, bm)
            return inst, candles, bm
    except Exception as exc:
        logger.warning("Candle sync note for %s: %s", clean, exc)

    return None, [], None

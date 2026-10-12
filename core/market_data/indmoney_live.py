"""Live prices for INDmoney-held assets, re-read from INDmoney itself.

Kite cannot price US stocks, NPS or INDmoney's own bookkeeping, but one INDmoney MCP call
(`get_family_asset_holdings`, about half a second) returns every holding with its current INR price and
1-day change. The Holdings page polls this on top of the stored holdings so those rows move too. Only
prices are overlaid; quantity and cost stay as stored, and a real sync remains the source of truth for them.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from core.models import Holding
from core.portfolio.normalization import NormalizationService
from providers.brokers.indmoney import IndmoneyProvider

logger = logging.getLogger("wealthvault.market_data.indmoney_live")

CACHE_SECONDS = 10.0
_cache: Dict[Tuple[str, str], Tuple[float, Dict[str, Holding]]] = {}


async def _fresh_for_connection(owner_id: str, connection_id: str) -> Dict[str, Holding]:
    key = (owner_id, connection_id)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    raw = await IndmoneyProvider(connection_id=connection_id).get_holdings()
    rows = NormalizationService().normalize_holdings(
        raw_data=raw, broker_name="indmoney", owner_id=owner_id, connection_id=connection_id
    )
    by_id = {h.holding_id: h for h in rows}
    _cache[key] = (time.monotonic(), by_id)
    return by_id


async def overlay_indmoney_live(owner_id: str, holdings: List[Holding]) -> List[Holding]:
    """Return `holdings` with INDmoney rows' prices and day change refreshed from INDmoney."""
    conn_ids = {h.connection_id for h in holdings if "indmoney" in (h.connection_id or "").lower()}
    fresh: Dict[str, Holding] = {}
    for conn_id in conn_ids:
        try:
            fresh.update(await _fresh_for_connection(owner_id, conn_id))
        except Exception as exc:  # auth expired, network: keep stored prices
            logger.warning("INDmoney live overlay skipped for %s: %s", conn_id, exc)

    out: List[Holding] = []
    for h in holdings:
        f = fresh.get(h.holding_id)
        if f is None or not f.current_value:
            out.append(h)
            continue
        invested = h.quantity * h.average_price
        out.append(
            h.model_copy(
                update={
                    "current_price": f.current_price,
                    "current_value": f.current_value,
                    "pnl": round(f.current_value - invested, 2),
                    "day_pnl": f.day_pnl,
                    "day_change_percentage": f.day_change_percentage,
                    "data_freshness": "live",
                    "last_price_updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
    return out

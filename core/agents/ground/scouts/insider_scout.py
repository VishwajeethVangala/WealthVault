"""Insider & Institutional Deals Scout: SEBI PIT and NSE Bulk/Block Deal Intelligence.

Monitors institutional accumulation and promoter transactions:
- Bulk deals (> 0.5% of total equity) executed on the exchange
- Block deals (> ₹5 Cr or 500,000 shares in designated window) by FIIs/DIIs/Mutual Funds
- SEBI PIT Regulation 7 insider disclosures by promoters and key managerial personnel

Uses a shared 1-hour cache for exchange-wide deal snapshots so 50+ stocks can be scanned
with zero redundant network queries to exchange endpoints.
"""

import csv
import io
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
import requests

from core.agents.forensic_crawler import clean_symbol
from core.agents.ground.contracts import BulkDealItem, InsiderIntelReport, PITDisclosureItem
from core.agents.ground.scouts.funda_scout import is_etf_instrument

logger = logging.getLogger("wealthvault.agents.ground.insider_scout")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Exchange-wide shared cache (TTL: 1 hour)
_DEALS_SNAPSHOT_CACHE: Tuple[float, Dict[str, Any]] = (0.0, {})
_PIT_CSV_CACHE: Tuple[float, List[Dict[str, str]]] = (0.0, [])


def _get_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/",
    })
    try:
        session.get("https://www.nseindia.com", timeout=5)
    except Exception as exc:
        logger.debug("NSE session prime note: %s", exc)
    return session


def _fetch_large_deals_snapshot() -> Dict[str, Any]:
    global _DEALS_SNAPSHOT_CACHE
    now = time.monotonic()
    cached_time, cached_data = _DEALS_SNAPSHOT_CACHE
    if now - cached_time < 3600.0 and cached_data:
        return cached_data

    try:
        session = _get_nse_session()
        url = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"
        resp = session.get(url, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            _DEALS_SNAPSHOT_CACHE = (now, data)
            return data
    except Exception as exc:
        logger.warning("NSE large deals snapshot fetch error: %s", exc)

    return {}


def _fetch_pit_disclosures() -> List[Dict[str, str]]:
    global _PIT_CSV_CACHE
    now = time.monotonic()
    cached_time, cached_rows = _PIT_CSV_CACHE
    if now - cached_time < 3600.0 and cached_rows:
        return cached_rows

    try:
        session = _get_nse_session()
        url = "https://www.nseindia.com/api/corporates-pit?index=equities&csv=true"
        resp = session.get(url, timeout=6)
        if resp.status_code == 200 and len(resp.text) > 200:
            f = io.StringIO(resp.text)
            reader = csv.reader(f)
            headers = [h.strip().replace("\n", "").strip() for h in next(reader, [])]
            rows = []
            for raw_row in reader:
                if len(raw_row) == len(headers):
                    rows.append({headers[i]: raw_row[i].strip() for i in range(len(headers))})
            _PIT_CSV_CACHE = (now, rows)
            return rows
    except Exception as exc:
        logger.debug("NSE PIT CSV fetch note: %s", exc)

    return []


class InsiderScout:
    """Scout for institutional block/bulk deals and promoter insider disclosures."""

    def evaluate(self, symbol: str) -> InsiderIntelReport:
        clean = clean_symbol(symbol)
        
        # 1. Bypass ETFs
        if is_etf_instrument(clean):
            return InsiderIntelReport(
                symbol=clean,
                is_etf=True,
                status="BYPASSED_ETF",
                summary="ETF / Index Basket: Insider & Bulk deals not applicable.",
            )

        try:
            snapshot = _fetch_large_deals_snapshot()
            raw_bulk = snapshot.get("BULK_DEALS_DATA", [])
            raw_block = snapshot.get("BLOCK_DEALS_DATA", [])

            # Filter for this specific stock
            bulk_items: List[BulkDealItem] = []
            block_items: List[BulkDealItem] = []
            
            inst_buy_qty = 0
            inst_sell_qty = 0

            for b in raw_bulk:
                sym = str(b.get("symbol") or "").strip().upper()
                if sym == clean:
                    buy_sell = "BUY" if str(b.get("buySell")).upper() == "BUY" else "SELL"
                    qty = int(str(b.get("qty") or "0").replace(",", ""))
                    price = float(str(b.get("watp") or "0").replace(",", ""))
                    if buy_sell == "BUY":
                        inst_buy_qty += qty
                    else:
                        inst_sell_qty += qty
                    bulk_items.append(
                        BulkDealItem(
                            date=str(b.get("date") or ""),
                            client_name=str(b.get("clientName") or "Institutional Investor"),
                            buy_sell=buy_sell,
                            quantity=qty,
                            price=price,
                            deal_type="BULK",
                            remarks=b.get("remarks"),
                        )
                    )

            for blk in raw_block:
                sym = str(blk.get("symbol") or "").strip().upper()
                if sym == clean:
                    buy_sell = "BUY" if str(blk.get("buySell")).upper() == "BUY" else "SELL"
                    qty = int(str(blk.get("qty") or "0").replace(",", ""))
                    price = float(str(blk.get("watp") or "0").replace(",", ""))
                    if buy_sell == "BUY":
                        inst_buy_qty += qty
                    else:
                        inst_sell_qty += qty
                    block_items.append(
                        BulkDealItem(
                            date=str(blk.get("date") or ""),
                            client_name=str(blk.get("clientName") or "Institutional Investor"),
                            buy_sell=buy_sell,
                            quantity=qty,
                            price=price,
                            deal_type="BLOCK",
                            remarks=blk.get("remarks"),
                        )
                    )

            # Filter PIT records
            pit_rows = _fetch_pit_disclosures()
            pit_items: List[PITDisclosureItem] = []
            promoter_buy_val = 0.0
            promoter_sell_val = 0.0

            for r in pit_rows:
                sym = r.get("SYMBOL", "").strip().upper()
                if sym == clean:
                    acq_type = r.get("TYPE OF SECURITY (ACQUIRED/DISPLOSED)", "").upper()
                    action = "BUY" if "ACQUI" in acq_type else ("SELL" if "DISP" in acq_type else "BUY")
                    qty = int(r.get("NO. OF SECURITIES (ACQUIRED/DISPLOSED)", "0") or "0")
                    val = float(r.get("VALUE OF SECURITY (ACQUIRED/DISPLOSED)", "0") or "0")
                    category = r.get("CATEGORY OF PERSON", "Promoter / Director")
                    if action == "BUY":
                        promoter_buy_val += val
                    else:
                        promoter_sell_val += val
                    pit_items.append(
                        PITDisclosureItem(
                            date=r.get("BROADCASTE DATE AND TIME", "")[:10],
                            person_name=r.get("NAME OF THE ACQUIRER/DISPOSER", "Insider"),
                            category_of_person=category,
                            transaction_type=action,
                            quantity=qty,
                            value_inr=val,
                        )
                    )

            # Determine institutional bias
            if inst_buy_qty > inst_sell_qty and inst_buy_qty > 0:
                inst_bias = "ACCUMULATION"
            elif inst_sell_qty > inst_buy_qty:
                inst_bias = "DISTRIBUTION"
            elif bulk_items or block_items:
                inst_bias = "NEUTRAL"
            else:
                inst_bias = "NO_DEALS"

            # Determine promoter bias
            if promoter_buy_val > promoter_sell_val and promoter_buy_val > 0:
                promoter_bias = "BUYING"
            elif promoter_sell_val > promoter_buy_val:
                promoter_bias = "SELLING"
            elif pit_items:
                promoter_bias = "NEUTRAL"
            else:
                promoter_bias = "NO_FILINGS"

            # Summary formulation
            summary_parts = []
            if bulk_items or block_items:
                summary_parts.append(
                    f"{len(bulk_items)} Bulk, {len(block_items)} Block deals (Institutional: {inst_bias})"
                )
            else:
                summary_parts.append("No institutional bulk/block deals in latest exchange session")

            if pit_items:
                summary_parts.append(f"SEBI PIT Insider Activity: {promoter_bias}")
            else:
                summary_parts.append("No recent promoter PIT filings")

            return InsiderIntelReport(
                symbol=clean,
                is_etf=False,
                bulk_deals=bulk_items,
                block_deals=block_items,
                pit_disclosures=pit_items,
                institutional_bias=inst_bias,
                promoter_bias=promoter_bias,
                status="COMPLETED",
                summary=" | ".join(summary_parts),
            )
        except Exception as exc:
            logger.warning("InsiderScout error for %s: %s", clean, exc)
            return InsiderIntelReport(
                symbol=clean,
                is_etf=False,
                status="FAILED",
                summary=f"Unable to parse exchange deal records: {str(exc)}",
            )

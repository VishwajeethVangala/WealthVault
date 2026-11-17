"""Fundamental Solvency Scout: Balance Sheet, ROCE & Debt-to-Equity.

Extracts financial statements and ratios from Screener.in:
- Return on Capital Employed (ROCE) and Return on Equity (ROE)
- Debt-to-Equity ratio & solvency safety
- 3-Year Sales Growth CAGR
- Promoter shareholding and pledged shares percentage

Automatically bypasses ETFs and index funds where corporate financials are not applicable.
"""

import logging
from typing import Optional

from core.agents.forensic_crawler import clean_symbol, fetch_fundamental_vitals
from core.agents.ground.contracts import FundaIntelReport

logger = logging.getLogger("wealthvault.agents.ground.funda_scout")

def is_etf_instrument(symbol: str) -> bool:
    """Detect whether a symbol represents an ETF rather than an individual equity."""
    s = symbol.upper()
    return (
        s.endswith("BEES")
        or s.endswith("ETF")
        or s.endswith("IETF")
        or s.startswith("SETF")
        or s.startswith("NETF")
        or s in {"GOLDBEES", "SILVERBEES", "NIFTYBEES", "BANKBEES", "JUNIORBEES", "LIQUIDBEES"}
    )


class FundaScout:
    """Scout for fundamental solvency and profitability ratios."""

    async def evaluate(self, symbol: str, company_name: Optional[str] = None) -> FundaIntelReport:
        clean = clean_symbol(symbol)
        
        # 1. Check for ETF bypass
        if is_etf_instrument(clean):
            return FundaIntelReport(
                symbol=clean,
                is_etf=True,
                status="BYPASSED_ETF",
                summary="ETF / Index Basket: Balance sheet & solvency analysis not applicable.",
            )

        # 2. Fetch from Screener.in via forensic crawler
        try:
            vitals = await fetch_fundamental_vitals(clean, company_name=company_name)
            
            # Format high-signal summary
            parts = []
            if vitals.market_cap_cr:
                parts.append(f"M-Cap: ₹{vitals.market_cap_cr:,.0f} Cr")
            if vitals.pe_ratio is not None:
                parts.append(f"P/E: {vitals.pe_ratio:.1f}")
            if vitals.roce_pct is not None:
                parts.append(f"ROCE: {vitals.roce_pct:.1f}%")
            if vitals.debt_to_equity is not None:
                parts.append(f"D/E: {vitals.debt_to_equity:.2f}")
            if vitals.sales_growth_yoy_pct is not None:
                parts.append(f"YoY Sales: {vitals.sales_growth_yoy_pct:+.1f}%")
            if vitals.promoter_holding_pct is not None:
                parts.append(f"Promoter: {vitals.promoter_holding_pct:.1f}%")
            if vitals.promoter_pledged_pct is not None and vitals.promoter_pledged_pct > 0:
                parts.append(f"Pledged: {vitals.promoter_pledged_pct:.1f}%")

            summary = " | ".join(parts) if parts else "Financial vitals retrieved from exchange filings."

            return FundaIntelReport(
                symbol=clean,
                is_etf=False,
                market_cap_cr=vitals.market_cap_cr,
                pe_ratio=vitals.pe_ratio,
                roce_pct=vitals.roce_pct,
                roe_pct=vitals.roe_pct,
                debt_to_equity=vitals.debt_to_equity,
                sales_growth_3y=vitals.sales_growth_yoy_pct,
                promoter_holding_pct=vitals.promoter_holding_pct,
                promoter_pledged_pct=vitals.promoter_pledged_pct,
                status="COMPLETED",
                summary=summary,
            )
        except Exception as exc:
            logger.warning("FundaScout error for %s: %s", clean, exc)
            return FundaIntelReport(
                symbol=clean,
                is_etf=False,
                status="FAILED",
                summary=f"Unable to parse balance sheet vitals: {str(exc)}",
            )

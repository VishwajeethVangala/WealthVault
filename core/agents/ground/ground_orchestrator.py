"""Ground-Level Scout Swarm Orchestration Engine.

Executes sequential, deliberate ground-level intelligence gathering:
- Runs scouts one-by-one per stock (Risk -> Tech -> Pattern -> Funda -> News -> Insider)
- Enforces gentle rate pacing (configurable 3s pause between stocks) to prevent rate limits
- Barrier synchronization gate enforces that all required scouts must report before a dossier is ready
- Persists dossiers to storage and provides live streaming progress for UI visualization
"""

import asyncio
import concurrent.futures
from datetime import datetime, timezone
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from core.agents.forensic_crawler import clean_display_name, clean_symbol
from core.agents.ground.candle_sync import get_or_sync_candles
from core.agents.ground.contracts import GroundStockDossier
from core.agents.ground.scouts.funda_scout import FundaScout, is_etf_instrument
from core.agents.ground.scouts.insider_scout import InsiderScout
from core.agents.ground.scouts.news_scout import NewsScout
from core.agents.ground.scouts.pattern_scout import PatternScout
from core.agents.ground.scouts.risk_scout import RiskScout
from core.agents.ground.scouts.tech_scout import TechScout
from storage.tables.repositories import GroundDossiersRepository

logger = logging.getLogger("wealthvault.agents.ground.orchestrator")

DEFAULT_OWNER = "demo_reviewer"
PRIMARY_OWNER = "google_109909149391234323377"

_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _run_sync(coro):
    """Run an async coroutine to completion and return its value synchronously.
    
    Safe whether called outside an event loop or inside an active event loop (e.g. FastAPI/Uvicorn).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        def worker():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        return _thread_pool.submit(worker).result()
    else:
        try:
            return asyncio.run(coro)
        except Exception as exc:
            logger.warning("Could not run sync table operation: %s", exc)
            return None


def _run_bg(coro):
    """Run an async coroutine in the background (fire-and-forget write)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        return asyncio.create_task(coro)
    else:
        def worker():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        _thread_pool.submit(worker)

# Known non-Indian / US stocks
KNOWN_US_TICKERS = {
    "MSFT", "AMZN", "NVDA", "DELL", "TSM", "TSMC", "LITE", "STX", "SPCX", "SPACEX",
    "THH", "PANW", "CRWD", "NEM", "PHAR", "MRVL", "SNDK", "ETN", "MU", "AMD",
    "PLTR", "PPLT", "VRTX", "BE", "NBIS", "URNM", "AAPL", "GOOGL", "GOOG", "META",
    "NFLX", "AVGO", "INTC", "QCOM", "TXN", "ARM", "ASML", "BABA", "BIDU", "PDD",
    "COIN", "MSTR", "HOOD", "UBER", "ABNB", "SNOW", "DDOG", "ZS", "NET",
    "MICRON", "ADVANCEDMI", "PALANTIRTE", "ABRDNPHYSI", "VERTEXPHAR", "BLOOMENERG",
    "MARVELL", "SANDISKCOR", "EATON", "NEBIUSGROU", "SPROTTURAN", "PALOALTONE",
    "CROWDSTRIK", "TRYHARDHOL", "NEWMONTMIN", "PHARMINGGR", "AMAZON", "SEAGATETEC",
    "DELLTECHNO", "LUMENTUMHO", "MICROSOFT"
}

# Known unlisted / private equity investments (no Kite/NSE market history)
KNOWN_UNLISTED_TICKERS = {
    "TONBOIMAGI", "TONBO", "SEDEMACMEC", "SEDEMAC", "BLUESTONEJ", "BLUESTONE",
    "KANOHARELE", "KANOHAR", "TRYHARDHOL", "TRYHARD", "ATHER", "ATHERENERG",
    "GROWW", "MONEYVIEW", "SPACEX"
}


def is_pure_equity_stock(
    symbol: str,
    name: str = "",
    asset_class: str = "",
    currency: str = "",
) -> bool:
    """Strictly filter for Indian publicly listed equities (NSE / BSE).
    
    Excludes:
    - US and foreign equities (MSFT, AMZN, NVDA, etc.)
    - Mutual funds and ETFs (all variants, index funds, savings funds, bees)
    - Gold / Silver / Commodities / SGBs
    - Unlisted / private equity investments (Tonbo, Sedemac, Bluestone, etc.)
    - Fixed income, debt, NPS, crypto
    """
    s = (symbol or "").strip().upper()
    n = (name or "").strip().upper()
    ac = str(asset_class or "").strip().upper()
    curr = str(currency or "").strip().upper()

    # Reject foreign currencies
    if curr and curr not in ("INR", ""):
        return False

    # Reject non-equity asset classes
    if any(k in ac for k in ["US_STOCK", "MUTUAL", "GOLD", "COMMODITY", "DEBT", "NPS", "CRYPTO"]):
        return False

    # Check ticker prefix in "TICKER (Company Name)"
    prefix_match = re.match(r"^([A-Z0-9]+)\s*\(", s)
    if prefix_match:
        prefix = prefix_match.group(1).strip()
        if prefix in KNOWN_US_TICKERS or prefix in KNOWN_UNLISTED_TICKERS:
            return False

    # Check clean symbol
    clean = clean_symbol(s)
    if clean in KNOWN_US_TICKERS or clean in KNOWN_UNLISTED_TICKERS:
        return False

    # Check unlisted company names
    unlisted_names = [
        "TONBO IMAGING", "SEDEMAC MECHATRONICS", "BLUESTONE JEWELLERY",
        "KANOHAR ELECTRICALS", "ATHER ENERGY", "TRYHARD", "SPACEX", "MONEYVIEW", "GROWW"
    ]
    if any(un in s or un in n for un in unlisted_names):
        return False

    # Check US company names
    us_names = [
        "MICROSOFT", "AMAZON", "NVIDIA", "DELL TECHNOLOGIES", "PALO ALTO",
        "CROWDSTRIKE", "PALANTIR", "MICRON", "ADVANCED MICRO", "BLOOM ENERGY",
        "SEAGATE", "LUMENTUM", "MARVELL", "SANDISK", "EATON", "NEBIUS",
        "SPROTT URANIUM", "NEWMONT", "PHARMING", "VERTEX PHARMA"
    ]
    if any(us in s or us in n for us in us_names):
        return False

    # Check Mutual Funds
    mf_indicators = [
        "DIRECT PLAN", "REGULAR PLAN", "MUTUAL", "FUND OF FUND", "SAVINGS FUND",
        "CONTRA FUND", "INDEX FUND", "FLEXI CAP", "SMALL CAP", "MID CAP", "LARGE CAP",
        "BALANCED ADVANTAGE", "SHORT TERM FUND"
    ]
    if any(m in s or m in n for m in mf_indicators):
        return False
    if s.startswith("INF") or clean.startswith("INF"):
        return False

    # Check Gold / SGB / ETF
    if (
        s.startswith("SGB")
        or s.endswith("-GB")
        or "BEES" in s
        or s.endswith("ETF")
        or s.endswith("IETF")
        or " ETF" in n
        or " ETF" in s
    ):
        return False

    return True


class GroundSwarmOrchestrator:
    """Coordinates sequential ground scouts with deliberate pacing and barrier checks."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path
        self.repo: GroundDossiersRepository = GroundDossiersRepository()
        self.risk_scout = RiskScout()
        self.tech_scout = TechScout()
        self.pattern_scout = PatternScout()
        self.funda_scout = FundaScout()
        self.news_scout = NewsScout()
        self.insider_scout = InsiderScout()

        self._dossiers: Dict[str, GroundStockDossier] = {}
        self._is_scanning: bool = False
        self._current_stock: Optional[str] = None
        self._current_scout: Optional[str] = None
        self._load_storage()

    def _load_storage(self, owner_id: Optional[str] = None) -> None:
        """Load stored ground dossiers from Azure Table Storage (or disk in explicit test mode)."""
        if self.storage_path and os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    loaded = {
                        sym: GroundStockDossier.model_validate(dos)
                        for sym, dos in data.items()
                    }
                    self._dossiers = {
                        sym: dos for sym, dos in loaded.items()
                        if is_pure_equity_stock(sym, name=dos.company_name)
                    }
            except Exception as exc:
                logger.warning("Failed to load ground dossiers from disk: %s", exc)
            return

        # Production path: Azure Table Storage
        target_owners = [owner_id] if owner_id else [PRIMARY_OWNER, DEFAULT_OWNER, "global"]
        for uid in target_owners:
            if not uid:
                continue
            try:
                dossiers = _run_sync(self.repo.list_dossiers(owner_id=uid))
                if dossiers:
                    self._dossiers = {
                        clean_symbol(dos.symbol).upper(): dos
                        for dos in dossiers
                        if is_pure_equity_stock(dos.symbol, name=dos.company_name)
                    }
                    logger.info("Loaded %d ground dossiers from Azure Table Storage for user %s", len(self._dossiers), uid)
                    break
            except Exception as exc:
                logger.warning("Azure Table load note for %s: %s", uid, exc)

    def _save_storage(self, owner_id: Optional[str] = None) -> None:
        """Persist ground dossiers to Azure Table Storage (or disk in explicit test mode)."""
        if self.storage_path:
            try:
                os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
                payload = {sym: dos.model_dump() for sym, dos in self._dossiers.items()}
                tmp_path = f"{self.storage_path}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                if os.path.exists(self.storage_path):
                    os.remove(self.storage_path)
                os.rename(tmp_path, self.storage_path)
            except Exception as exc:
                logger.warning("Failed to persist ground dossiers to disk: %s", exc)
        else:
            target_owner = (owner_id or PRIMARY_OWNER).strip()
            if self._dossiers:
                _run_bg(self.repo.batch_upsert_dossiers(target_owner, list(self._dossiers.values())))

    def _save_single_dossier(self, dossier: GroundStockDossier, owner_id: Optional[str] = None) -> None:
        """Persist a single updated dossier to Azure Table Storage immediately."""
        clean = clean_symbol(dossier.symbol).upper()
        self._dossiers[clean] = dossier
        if self.storage_path:
            self._save_storage()
        else:
            target_owner = (owner_id or PRIMARY_OWNER).strip()
            _run_bg(self.repo.upsert_dossier(target_owner, dossier))

    def get_all_dossiers(self, owner_id: Optional[str] = None) -> List[GroundStockDossier]:
        """Return all current ground dossiers."""
        if not self._dossiers:
            self._load_storage(owner_id)
        return list(self._dossiers.values())

    def get_dossier(self, symbol: str, owner_id: Optional[str] = None) -> Optional[GroundStockDossier]:
        """Return the dossier for a specific symbol."""
        if not self._dossiers:
            self._load_storage(owner_id)
        clean = clean_symbol(symbol).upper()
        d = self._dossiers.get(clean)
        if d:
            return d
        # Common dual-listing aliases (NSE <-> BSE / symbol variations)
        aliases = {
            "DIACABS": "DIAMONDYD",
            "DIAMONDYD": "DIACABS",
            "BBL": "BHARATBIJLEE",
            "BHARATBIJLEE": "BBL",
            "IND-SWIFT": "INDSWFTLAB",
            "INDSWFT": "INDSWFTLAB",
        }
        alt = aliases.get(clean)
        if alt and alt in self._dossiers:
            return self._dossiers[alt]
        return None

    def get_status(self) -> Dict[str, Any]:
        """Return live swarm scanning status."""
        total = len(self._dossiers)
        ready = sum(1 for d in self._dossiers.values() if d.barrier_status == "READY_FOR_REVIEW")
        return {
            "is_scanning": self._is_scanning,
            "current_stock": self._current_stock,
            "current_scout": self._current_scout,
            "total_dossiers": total,
            "ready_dossiers": ready,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def scan_single_stock(
        self,
        holding: Dict[str, Any],
        total_portfolio_value: float,
        owner_id: Optional[str] = None,
    ) -> GroundStockDossier:
        """Run all 6 scouts sequentially for a single stock."""
        raw_sym = str(holding.get("tradingsymbol") or holding.get("symbol") or "UNKNOWN")
        clean = clean_symbol(raw_sym)
        disp_name = str(holding.get("name") or clean_display_name(raw_sym) or clean)
        is_etf = is_etf_instrument(clean)

        # Fresh in-place dossier: purges previous intermediate state so clean replacement occurs
        dossier = GroundStockDossier(
            symbol=clean,
            company_name=disp_name,
            is_etf=is_etf,
        )
        dossier.barrier_status = "IN_PROGRESS"
        self._dossiers[clean] = dossier
        self._current_stock = clean

        # Pre-fetch / sync candles to table storage
        _, candles, bm = await get_or_sync_candles(clean, owner_id=owner_id, lookback_days=400)

        # 1. Risk Scout
        self._current_scout = "risk"
        dossier.current_scout = "Risk Scout"
        dossier.risk_report = self.risk_scout.evaluate_holding(holding, total_portfolio_value)
        dossier.update_barrier()
        self._save_single_dossier(dossier, owner_id=owner_id)

        # 2. Technical Scout
        self._current_scout = "tech"
        dossier.current_scout = "Technical Scout"
        dossier.tech_report = self.tech_scout.evaluate(clean, candles, benchmark_candles=bm)
        dossier.update_barrier()
        self._save_single_dossier(dossier, owner_id=owner_id)

        # 3. Pattern Scout
        self._current_scout = "pattern"
        dossier.current_scout = "Pattern Scout"
        dossier.pattern_report = self.pattern_scout.evaluate(clean, candles)
        dossier.update_barrier()
        self._save_single_dossier(dossier, owner_id=owner_id)

        # 4. Fundamental Scout (bypasses ETFs)
        self._current_scout = "funda"
        dossier.current_scout = "Fundamental Scout"
        dossier.funda_report = await self.funda_scout.evaluate(clean, company_name=disp_name)
        dossier.update_barrier()
        self._save_single_dossier(dossier, owner_id=owner_id)

        # 5. Forensic News Scout
        self._current_scout = "news"
        dossier.current_scout = "News Scout"
        dossier.news_report = await self.news_scout.evaluate(clean, company_name=disp_name)
        dossier.update_barrier()
        self._save_single_dossier(dossier, owner_id=owner_id)

        # 6. Insider & Deals Scout (bypasses ETFs)
        self._current_scout = "insider"
        dossier.current_scout = "Insider Scout"
        dossier.insider_report = self.insider_scout.evaluate(clean)
        dossier.update_barrier()
        self._save_single_dossier(dossier, owner_id=owner_id)

        dossier.current_scout = None
        self._current_stock = None
        self._current_scout = None
        return dossier

    async def run_swarm_cycle(
        self,
        holdings: List[Dict[str, Any]],
        total_portfolio_value: float,
        owner_id: Optional[str] = None,
        inter_stock_delay: float = 3.0,
    ) -> List[GroundStockDossier]:
        """Execute a calm, deliberate scan across pure equity stocks, completely excluding ETFs and MFs."""
        if self._is_scanning:
            logger.info("Ground swarm scan already in progress.")
            return self.get_all_dossiers()

        # Strict filter: ONLY pure Indian equity stocks
        equity_holdings = [
            h for h in holdings
            if is_pure_equity_stock(
                str(h.get("tradingsymbol") or h.get("symbol") or ""),
                name=str(h.get("name") or ""),
                asset_class=str(h.get("asset_class") or ""),
                currency=str(h.get("currency") or ""),
            )
        ]

        self._is_scanning = True
        try:
            results = []
            for i, h in enumerate(equity_holdings):
                dos = await self.scan_single_stock(h, total_portfolio_value, owner_id=owner_id)
                results.append(dos)

                # User requested: Deliberate 3-second break between stocks
                if i < len(equity_holdings) - 1 and inter_stock_delay > 0:
                    await asyncio.sleep(inter_stock_delay)

            return results
        finally:
            self._is_scanning = False
            self._current_stock = None
            self._current_scout = None
            self._save_storage()


_SWARM_ORCHESTRATOR: Optional[GroundSwarmOrchestrator] = None


def get_ground_swarm_orchestrator() -> GroundSwarmOrchestrator:
    """Singleton getter for the Ground Swarm Orchestrator."""
    global _SWARM_ORCHESTRATOR
    if _SWARM_ORCHESTRATOR is None:
        _SWARM_ORCHESTRATOR = GroundSwarmOrchestrator()
    return _SWARM_ORCHESTRATOR

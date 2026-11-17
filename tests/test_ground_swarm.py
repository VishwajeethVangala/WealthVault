"""Unit tests for the Ground-Level Scout Swarm & Barrier Synchronization."""

import pytest
from core.agents.ground.contracts import (
    FundaIntelReport,
    GroundStockDossier,
    InsiderIntelReport,
    NewsIntelReport,
    PatternIntelReport,
    RiskIntelReport,
    TechIntelReport,
)
from core.agents.ground.finbert_engine import classify_headline
from core.agents.ground.scouts.funda_scout import FundaScout, is_etf_instrument
from core.agents.ground.scouts.insider_scout import InsiderScout
from core.agents.ground.scouts.pattern_scout import PatternScout
from core.agents.ground.scouts.risk_scout import RiskScout
from core.agents.ground.scouts.tech_scout import TechScout


def test_risk_scout_breach_detection():
    scout = RiskScout()
    # Breach holding: buy at 100, current at 90 (-10% -> stop breach)
    holding = {
        "tradingsymbol": "TESTSTOCK",
        "average_price": 100.0,
        "last_price": 90.0,
        "quantity": 50,
        "broker": "Zerodha Kite",
    }
    rep = scout.evaluate_holding(holding, total_portfolio_value=50000.0)
    assert rep.symbol == "TESTSTOCK"
    assert rep.pnl_pct == -10.0
    assert rep.stop_loss_breach is True
    assert rep.deep_drawdown_breach is False
    assert "Hard Stop Breach" in rep.summary


def test_risk_scout_safe_holding():
    scout = RiskScout()
    # Safe holding: buy at 100, current at 115 (+15%)
    holding = {
        "tradingsymbol": "RELIANCE",
        "average_price": 100.0,
        "last_price": 115.0,
        "quantity": 100,
        "broker": "Groww",
    }
    rep = scout.evaluate_holding(holding, total_portfolio_value=100000.0)
    assert rep.symbol == "RELIANCE"
    assert rep.pnl_pct == 15.0
    assert rep.stop_loss_breach is False
    assert "Normal Operating Range" in rep.summary


def test_tech_scout_uptrend():
    scout = TechScout()
    # 250 upward daily candles
    candles = [
        {"date": f"2026-01-{i+1:03d}", "open": 100 + i, "high": 105 + i, "low": 98 + i, "close": 102 + i, "volume": 1000}
        for i in range(250)
    ]
    rep = scout.evaluate("TESTSYM", candles)
    assert rep.symbol == "TESTSYM"
    assert rep.status == "COMPLETED"
    assert rep.momentum_score >= 4
    assert "Stage 2: Markup" in rep.stage_verdict


def test_pattern_scout_ascending_triangle():
    scout = PatternScout()
    # Construct an ascending triangle: resistance at 150, lows rising 130 -> 138 -> 144
    candles = []
    # 30 base candles
    for i in range(30):
        candles.append({"date": f"2026-01-{i:02d}", "open": 130, "high": 135, "low": 128, "close": 132, "volume": 1000})

    # Wave 1: peak at 150, low at 132
    candles.extend([
        {"date": "2026-02-01", "open": 135, "high": 142, "low": 134, "close": 140, "volume": 1200},
        {"date": "2026-02-02", "open": 140, "high": 150, "low": 139, "close": 149, "volume": 2000}, # Peak 1
        {"date": "2026-02-03", "open": 148, "high": 148, "low": 140, "close": 142, "volume": 800},
        {"date": "2026-02-04", "open": 141, "high": 142, "low": 132, "close": 134, "volume": 600},  # Low 1
    ])

    # Wave 2: peak at 150, low at 140
    candles.extend([
        {"date": "2026-02-05", "open": 135, "high": 144, "low": 134, "close": 142, "volume": 900},
        {"date": "2026-02-06", "open": 143, "high": 150, "low": 142, "close": 149, "volume": 1500}, # Peak 2
        {"date": "2026-02-07", "open": 148, "high": 148, "low": 142, "close": 144, "volume": 700},
        {"date": "2026-02-08", "open": 143, "high": 144, "low": 140, "close": 141, "volume": 500},  # Low 2 (higher low!)
        {"date": "2026-02-09", "open": 142, "high": 148, "low": 142, "close": 147, "volume": 1100},
    ])

    rep = scout.evaluate("TRIANGLE_SYM", candles)
    assert rep.symbol == "TRIANGLE_SYM"
    # Should detect pattern or return clean report
    assert rep.status == "COMPLETED"


def test_funda_scout_etf_bypass():
    scout = FundaScout()
    assert is_etf_instrument("SILVERBEES") is True
    assert is_etf_instrument("GOLDBEES") is True
    assert is_etf_instrument("NIFTYBEES") is True
    assert is_etf_instrument("RELIANCE") is False

    import asyncio
    rep = asyncio.run(scout.evaluate("SILVERBEES"))
    assert rep.is_etf is True
    assert rep.status == "BYPASSED_ETF"
    assert "ETF" in rep.summary


def test_insider_scout_etf_bypass():
    scout = InsiderScout()
    rep = scout.evaluate("GOLDBEES")
    assert rep.is_etf is True
    assert rep.status == "BYPASSED_ETF"
    assert "ETF" in rep.summary


def test_finbert_classifier():
    label, conf = classify_headline("Tata Motors profit jumps 45% as JLR margins expand")
    assert label == "POSITIVE"
    assert conf > 0.5

    label2, conf2 = classify_headline("SEBI launches probe into financial fraud and raids offices")
    assert label2 == "NEGATIVE"
    assert conf2 > 0.5


def test_barrier_gate_synchronization():
    # 1. Equity dossier requires all 6 scouts
    dossier = GroundStockDossier(symbol="PASHUPATI", is_etf=False)
    dossier.update_barrier()
    assert dossier.barrier_status == "PENDING"
    assert len(dossier.required_scouts) == 6

    # Add 3 scouts
    dossier.risk_report = RiskIntelReport(symbol="PASHUPATI", status="COMPLETED")
    dossier.tech_report = TechIntelReport(symbol="PASHUPATI", status="COMPLETED")
    dossier.pattern_report = PatternIntelReport(symbol="PASHUPATI", status="COMPLETED")
    dossier.update_barrier()
    assert dossier.barrier_status == "IN_PROGRESS"
    assert len(dossier.missing_scouts) == 3

    # Add remaining 3 scouts
    dossier.funda_report = FundaIntelReport(symbol="PASHUPATI", status="COMPLETED")
    dossier.news_report = NewsIntelReport(symbol="PASHUPATI", status="COMPLETED")
    dossier.insider_report = InsiderIntelReport(symbol="PASHUPATI", status="COMPLETED")
    dossier.update_barrier()
    assert dossier.barrier_status == "READY_FOR_REVIEW"
    assert len(dossier.missing_scouts) == 0

    # 2. ETF dossier requires only 4 scouts (funda and insider auto-bypassed)
    etf_dossier = GroundStockDossier(symbol="SILVERBEES", is_etf=True)
    etf_dossier.risk_report = RiskIntelReport(symbol="SILVERBEES", status="COMPLETED")
    etf_dossier.tech_report = TechIntelReport(symbol="SILVERBEES", status="COMPLETED")
    etf_dossier.pattern_report = PatternIntelReport(symbol="SILVERBEES", status="COMPLETED")
    etf_dossier.news_report = NewsIntelReport(symbol="SILVERBEES", status="COMPLETED")
    etf_dossier.update_barrier()
    assert etf_dossier.barrier_status == "READY_FOR_REVIEW"


def test_pattern_scout_volume_surge_and_bull_trap():
    from core.agents.ground.scouts.pattern_scout import _evaluate_volume_signature
    import numpy as np

    # 20 days with 10,000 avg volume
    vols = np.array([10000.0] * 20 + [25000.0])  # Today volume is 25k (2.5x surge)
    surge, dryup, is_trap, delta, note = _evaluate_volume_signature(vols, is_near_pivot=False, is_breakout=True)
    assert surge == 2.5
    assert is_trap is False
    assert delta == 10
    assert "Verified institutional volume surge" in note

    # Low volume breakout (only 6k vs 10k avg -> 0.6x)
    vols_trap = np.array([10000.0] * 20 + [6000.0])
    surge_trap, _, is_trap2, delta_trap, note_trap = _evaluate_volume_signature(vols_trap, is_near_pivot=False, is_breakout=True)
    assert surge_trap == 0.6
    assert is_trap2 is True
    assert delta_trap == -35
    assert "Retail Bull Trap" in note_trap


def test_tech_scout_market_regime():
    from core.agents.ground.scouts.tech_scout import _classify_market_regime

    # Uptrend Nifty: 21,000 -> 24,000
    bull_candles = [{"date": f"2026-01-{i:03d}", "close": 21000 + i * 40} for i in range(100)]
    regime, summary = _classify_market_regime(bull_candles)
    assert regime == "BULL_MARKET"
    assert "Risk-On Regime" in summary

    # Downtrend Nifty: 25,000 -> 20,000
    bear_candles = [{"date": f"2026-01-{i:03d}", "close": 25000 - i * 50} for i in range(100)]
    regime_bear, summary_bear = _classify_market_regime(bear_candles)
    assert regime_bear == "BEAR_CORRECTION"
    assert "Defensive Regime" in summary_bear


def test_indmoney_ticker_normalization():
    from core.agents.forensic_crawler import clean_symbol

    cases = {
        "INDS03339 (Paras Defence and Space Technologies Ltd)": "PARAS",
        "INDS00188 (Bharat Heavy Electricals Ltd)": "BHEL",
        "INDS02017 (Mawana Sugars Ltd)": "MAWANASUG",
        "INDS04293 (Diamond Power Infrastructure Ltd)": "DIACABS",
        "INDS03808 (Lloyds Engineering Works Ltd)": "LLOYDSENGG",
        "INDS03761 (Adani Total Gas Ltd)": "ATGL",
        "INDS38467 (Anlon Healthcare Ltd)": "ANLON",
        "INDS02714 (Transformers & Rectifiers India Ltd)": "TARIL",
        "INDS28108 (Tata Technologies Ltd)": "TATATECH",
        "INDS28550 (Azad Engineering Ltd)": "AZAD",
        "INDS04329 (GACM Technologies Ltd)": "GATECH",
        "INDS34199 (One Mobikwik Systems Ltd)": "MOBIKWIK",
        "INDS00876 (Cupid Ltd)": "CUPID",
        "INDS02882 (Ind-Swift Laboratories Ltd)": "INDSWFTLAB",
        "INDS02929 (Sona BLW Precision Forgings Ltd)": "SONACOMS",
        "INDS3107 (Wockhardt Ltd)": "WOCKPHARMA",
        "INDS00168 (Bharat Bijlee Ltd)": "BBL",
        "INDS26499 (Netweb Technologies India Ltd)": "NETWEB",
        "INDS02298 (Va Tech Wabag Ltd)": "WABAG",
        "INDS31402 (DEE Development Engineers Ltd)": "DEEDEV",
        "INDS28474 (Motisons Jewellers Ltd)": "MOTISONS",
        "INDS00330 (Ugar Sugar Works Ltd)": "UGARSUGAR",
        "INDS03323 (Magadh Sugar & Energy Ltd)": "MAGADSUGAR",
        "TBZ-BE": "TBZ",
        "MOREPENLAB-BE": "MOREPENLAB",
        "HFCL-BE": "HFCL",
        "NSE:OLAELEC": "OLAELEC",
    }
    for raw, expected in cases.items():
        assert clean_symbol(raw) == expected, f"Failed for {raw}: got {clean_symbol(raw)} vs expected {expected}"


def test_strict_indian_equity_filter():
    from core.agents.ground.ground_orchestrator import is_pure_equity_stock

    # US Stocks - MUST be rejected
    assert is_pure_equity_stock("MSFT (Microsoft)", asset_class="US_STOCKS") is False
    assert is_pure_equity_stock("NVDA", asset_class="US_STOCKS") is False
    assert is_pure_equity_stock("AMZN (Amazon)") is False
    assert is_pure_equity_stock("MU (Micron)") is False
    assert is_pure_equity_stock("THH (TryHard Holdings Limited)") is False
    assert is_pure_equity_stock("RELIANCE", currency="USD") is False

    # Unlisted Private Equity - MUST be rejected
    assert is_pure_equity_stock("INDS45245 (Tonbo Imaging India Ltd)") is False
    assert is_pure_equity_stock("INDS41627 (Sedemac Mechatronics Ltd)") is False
    assert is_pure_equity_stock("INDS38239 (Bluestone Jewellery & Lifestyle Ltd)") is False
    assert is_pure_equity_stock("INDS44580 (Kanohar Electricals Ltd)") is False
    assert is_pure_equity_stock("INDS36409 (Ather Energy Ltd)") is False
    assert is_pure_equity_stock("MONEYVIEW") is False
    assert is_pure_equity_stock("GROWW") is False

    # Mutual Funds & ETFs & Gold - MUST be rejected
    assert is_pure_equity_stock("PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN", asset_class="MUTUAL_FUND") is False
    assert is_pure_equity_stock("HDFC MID CAP FUND - DIRECT PLAN") is False
    assert is_pure_equity_stock("SGBJUN31I-GB", asset_class="GOLD") is False
    assert is_pure_equity_stock("SILVERBEES") is False
    assert is_pure_equity_stock("GOLDBEES") is False

    # Pure Indian Listed Equities - MUST be accepted
    assert is_pure_equity_stock("INDS03339 (Paras Defence and Space Technologies Ltd)", asset_class="EQUITY", currency="INR") is True
    assert is_pure_equity_stock("INDS00188 (Bharat Heavy Electricals Ltd)", asset_class="EQUITY", currency="INR") is True
    assert is_pure_equity_stock("ICICIBANK", asset_class="EQUITY", currency="INR") is True
    assert is_pure_equity_stock("SHANTIGOLD", asset_class="EQUITY", currency="INR") is True
    assert is_pure_equity_stock("TBZ-BE", asset_class="EQUITY", currency="INR") is True



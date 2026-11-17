"""Unit and integration tests for the WealthVault Multi-Level Agent Hierarchy."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routers.accounts import get_current_user
from core.agents.boss import FinancialPlanningBossAgent
from core.agents.forensic_crawler import calculate_market_causality, clean_symbol
from core.agents.models import (
    DirectiveCard,
    DirectivePriority,
    DirectiveStatus,
    FundamentalVitals,
    InvestigationDossier,
    MoveCausality,
    NewsCatalyst,
    ProposalActionType,
    ProposedAction,
    WorkProposal,
)
from core.agents.orchestrator import BoardroomOrchestrator
from core.agents.reviewer import FiduciaryReviewerAgent
from core.agents.risk_officer import RiskOfficerAgent
from core.agents.storage import BoardroomStorage


def test_symbol_cleaner():
    """Verify ticker normalization across formats."""
    assert clean_symbol("NSE:OLAELEC") == "OLAELEC"
    assert clean_symbol("BSE:RELIANCE") == "RELIANCE"
    assert clean_symbol("MOREPENLAB-BE") == "MOREPENLAB"
    assert clean_symbol("INDS03339 (Ola Electric)") == "OLAELEC"
    assert clean_symbol("INDS02425 (Shipping Corporation of India Ltd)") == "SCI"


def test_market_causality_calculation():
    """Verify market beta decomposition vs idiosyncratic company shock."""
    # Sharp drop with market crash -> systemic
    c1, exp1 = calculate_market_causality(stock_move_pct=-8.0, benchmark_move_pct=-2.5)
    assert c1 == MoveCausality.SYSTEMIC_MARKET_BETA
    assert "broad market" in exp1.lower()

    # Sharp drop with stable market -> company specific
    c2, exp2 = calculate_market_causality(stock_move_pct=-8.0, benchmark_move_pct=+0.2)
    assert c2 == MoveCausality.COMPANY_SPECIFIC
    assert "idiosyncratic" in exp2.lower()


def test_risk_officer_detects_stop_loss():
    """Risk Officer must flag stop-loss breach when position is down >= 7.5%."""
    ro = RiskOfficerAgent()
    # 1 loser (down 9%), plus 10 small balanced holdings (each 9% of portfolio, no concentration breaches)
    holdings = [
        {
            "symbol": "NSE:LOSER",
            "quantity": 10,
            "average_price": 100.0,
            "last_price": 91.0,  # value: 910
            "broker": "zerodha"
        }
    ]
    for i in range(10):
        holdings.append({
            "symbol": f"NSE:STOCK{i}",
            "quantity": 10,
            "average_price": 100.0,
            "last_price": 100.0,  # value: 1000
            "broker": "groww"
        })
    total_val = 910 + 10 * 1000  # 10,910
    proposals = ro.analyze_holdings(holdings, total_portfolio_value=total_val)

    # Exactly 1 proposal for the stop-loss breach
    cut_loss_proposals = [p for p in proposals if p.proposed_actions[0].action == ProposalActionType.CUT_LOSS]
    assert len(cut_loss_proposals) == 1
    prop = cut_loss_proposals[0]
    assert prop.source_agent_id == "risk_officer"
    assert prop.proposed_actions[0].symbol == "NSE:LOSER"
    assert "Stop-Loss Breach" in prop.thesis


def test_risk_officer_detects_overweight_concentration():
    """Risk Officer must flag position exceeding 15% concentration ceiling."""
    ro = RiskOfficerAgent()
    # 1 giant holding (50% of portfolio) + 10 small holdings (5% each)
    holdings = [
        {
            "symbol": "NSE:GIANT",
            "quantity": 500,
            "average_price": 100.0,
            "last_price": 100.0,  # value: 50,000 (50% of 100k)
            "broker": "indmoney"
        }
    ]
    for i in range(10):
        holdings.append({
            "symbol": f"NSE:SMALL{i}",
            "quantity": 50,
            "average_price": 100.0,
            "last_price": 100.0,  # value: 5,000 (5% each)
            "broker": "zerodha"
        })
    proposals = ro.analyze_holdings(holdings, total_portfolio_value=100000.0)
    assert len(proposals) == 1
    assert proposals[0].proposed_actions[0].symbol == "NSE:GIANT"
    assert proposals[0].proposed_actions[0].action == ProposalActionType.TRAILING_TRIM
    assert "Concentration Overweight" in proposals[0].thesis


def test_reviewer_forensic_audit_and_dossier():
    """Reviewer Agent evaluates proposal and generates forensic evaluation."""
    async def _run():
        rev = FiduciaryReviewerAgent()
        prop = WorkProposal(
            proposal_id="prop_test_1",
            source_agent_id="risk_officer",
            source_agent_name="The Risk Officer",
            thesis="Position down -8.5%",
            underlying_metrics={"pnl_pct": -8.5},
            proposed_actions=[
                ProposedAction(
                    symbol="OLAELEC",
                    broker="zerodha",
                    action=ProposalActionType.CUT_LOSS,
                    quantity=100,
                    estimated_price=35.0,
                    trigger_reason="Stop loss breach"
                )
            ]
        )

        mock_dossier = InvestigationDossier(
            symbol="OLAELEC",
            causality=MoveCausality.COMPANY_SPECIFIC,
            causality_explanation="Company specific shock",
            recent_news=[
                NewsCatalyst(headline="Earnings miss", source="Reuters", published_at="Today", sentiment="NEGATIVE")
            ],
            fundamental_vitals=FundamentalVitals(roce_pct=-15.0),
            purpose_of_move="Earnings contraction",
            forensic_risk_score=75
        )

        with patch("core.agents.reviewer.build_investigation_dossier", new=AsyncMock(return_value=mock_dossier)):
            evaluation = await rev.audit_proposal(prop, benchmark_nifty_move_pct=-0.2)
            assert evaluation.proposal_id == "prop_test_1"
            assert evaluation.verdict == "APPROVED"
            assert evaluation.passed_rules_count >= 4
            assert evaluation.investigation_dossier.forensic_risk_score == 75

    asyncio.run(_run())


def test_boss_synthesizes_directive_card():
    """Boss Agent converts approved proposal into actionable DirectiveCard."""
    boss = FinancialPlanningBossAgent()
    prop = WorkProposal(
        proposal_id="prop_test_2",
        source_agent_id="risk_officer",
        source_agent_name="The Risk Officer",
        urgency=DirectivePriority.HIGH,
        thesis="Exit loser",
        proposed_actions=[
            ProposedAction(
                symbol="NSE:TEST",
                broker="groww",
                action=ProposalActionType.CUT_LOSS,
                quantity=50,
                estimated_price=200.0,
                trigger_reason="Stop loss breach"
            )
        ]
    )
    from core.agents.models import ReviewEvaluation
    evaluation = ReviewEvaluation(
        evaluation_id="eval_test_2",
        proposal_id="prop_test_2",
        verdict="APPROVED",
        critique_and_feedback="All policies passed"
    )

    directive = boss.synthesize_directive(prop, evaluation)
    assert directive is not None
    assert "Cut Loss: TEST (Groww)" in directive.title
    assert directive.user_status == DirectiveStatus.PENDING_REVIEW
    assert "Capital Redeployment" in directive.summary_thesis


def test_reviewer_false_breakdown_protection():
    """Reviewer detects structural 200-DMA support and institutional accumulation on a stop-loss proposal."""
    from core.agents.ground.contracts import GroundStockDossier, TechIntelReport, InsiderIntelReport, NewsIntelReport
    from core.agents.ground.ground_orchestrator import get_ground_swarm_orchestrator
    import asyncio

    orch = get_ground_swarm_orchestrator()
    dossier = GroundStockDossier(symbol="SAFEACCUM", company_name="Safe Accumulation Ltd")
    dossier.tech_report = TechIntelReport(
        symbol="SAFEACCUM",
        current_price=102.0,
        sma_200=100.0,
        slope_200_sma=2.5,
        stage_verdict="Stage 2: Markup",
    )
    dossier.insider_report = InsiderIntelReport(
        symbol="SAFEACCUM",
        institutional_bias="ACCUMULATION",
    )
    dossier.news_report = NewsIntelReport(
        symbol="SAFEACCUM",
        material_threat=False,
    )
    orch._dossiers["SAFEACCUM"] = dossier

    reviewer = FiduciaryReviewerAgent()
    prop = WorkProposal(
        proposal_id="prop_breakdown_1",
        source_agent_id="risk_officer",
        source_agent_name="The Risk Officer",
        urgency=DirectivePriority.HIGH,
        thesis="Exit loser",
        proposed_actions=[
            ProposedAction(
                symbol="SAFEACCUM",
                broker="zerodha",
                action=ProposalActionType.CUT_LOSS,
                quantity=100,
                estimated_price=102.0,
                trigger_reason="Stop loss breach",
            )
        ],
        revision_round=0,
    )

    evaluation = asyncio.run(reviewer.audit_proposal(prop))
    assert evaluation.verdict == "REVISION_REQUIRED"
    assert "False Breakdown Protection" in evaluation.critique_and_feedback


def test_directive_status_update_closure():
    """User can mark a directive closed ('ORDER_PLACED_AT_BROKER', 'IGNORED')."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = BoardroomStorage(filepath=Path(tmpdir) / "test_boardroom.json")
        card = DirectiveCard(
            directive_id="dir_001",
            title="Trim ABC",
            summary_thesis="Rebalance",
            priority=DirectivePriority.HIGH
        )
        storage.save_directive(card)

        # Mark closed as ORDER_PLACED_AT_BROKER
        updated = storage.update_directive_status("dir_001", DirectiveStatus.ORDER_PLACED_AT_BROKER, "Executed on Kite")
        assert updated.user_status == DirectiveStatus.ORDER_PLACED_AT_BROKER
        assert updated.resolved_at is not None

        # Verify persistence
        reloaded = storage.get_directive("dir_001")
        assert reloaded.user_status == DirectiveStatus.ORDER_PLACED_AT_BROKER


def test_api_boardroom_endpoints():
    """Verify FastAPI boardroom endpoints with TestClient."""
    app.dependency_overrides[get_current_user] = lambda: "test_user_123"
    client = TestClient(app)

    # 1. Get Boardroom Overview
    res = client.get("/api/v1/agents/boardroom")
    assert res.status_code == 200
    data = res.json()
    assert "agents" in data
    assert len(data["agents"]) == 3  # Boss, Reviewer, Risk Officer
    assert "timeline" in data

    # 2. Get Stock Dossier
    mock_dossier = InvestigationDossier(
        symbol="TCS",
        causality=MoveCausality.SYSTEMIC_MARKET_BETA,
        causality_explanation="Stable",
        purpose_of_move="Consolidation",
        forensic_risk_score=15
    )
    with patch("apps.api.routers.agents.build_investigation_dossier", new=AsyncMock(return_value=mock_dossier)):
        dossier_res = client.get("/api/v1/agents/dossier/TCS")
        assert dossier_res.status_code == 200
        dossier_data = dossier_res.json()
        assert dossier_data["symbol"] == "TCS"
        assert dossier_data["forensic_risk_score"] == 15

    # 3. Test POST /api/v1/agents/run with canonical Holding entities
    from core.models import Holding, AssetClass
    mock_holdings = [
        Holding(
            holding_id="hold_01",
            owner_id="test_user_123",
            connection_id="conn_zerodha_live",
            instrument_symbol="NSE:OLAELEC",
            asset_class=AssetClass.EQUITY,
            quantity=100.0,
            average_price=45.0,
            current_price=35.0,
            current_value=3500.0
        ),
        Holding(
            holding_id="hold_02",
            owner_id="test_user_123",
            connection_id="conn_groww_live",
            instrument_symbol="NSE:TITAN",
            asset_class=AssetClass.EQUITY,
            quantity=10.0,
            average_price=3000.0,
            current_price=3200.0,
            current_value=32000.0
        )
    ]
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        temp_storage_path = tf.name

    temp_storage = BoardroomStorage(filepath=Path(temp_storage_path))

    with patch("storage.tables.repositories.HoldingsRepository.get_holdings", new=AsyncMock(return_value=mock_holdings)), \
         patch("core.agents.forensic_crawler.build_investigation_dossier", new=AsyncMock(return_value=mock_dossier)), \
         patch("core.agents.storage.get_boardroom_storage", return_value=temp_storage), \
         patch("core.agents.orchestrator.get_boardroom_storage", return_value=temp_storage), \
         patch("apps.api.routers.agents.get_boardroom_storage", return_value=temp_storage):
        run_res = client.post("/api/v1/agents/run")
        assert run_res.status_code == 200
        run_data = run_res.json()
        assert "agents" in run_data
        assert "timeline" in run_data

        # 4. Run review again and verify no duplicate directives are created
        run_res_2 = client.post("/api/v1/agents/run")
        assert run_res_2.status_code == 200
        run_data_2 = run_res_2.json()
        assert len(run_data_2["active_directives"]) == len(run_data["active_directives"])

    try:
        Path(temp_storage_path).unlink(missing_ok=True)
    except Exception:
        pass

    app.dependency_overrides.clear()

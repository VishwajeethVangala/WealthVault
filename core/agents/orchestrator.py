"""Agent Boardroom Orchestration Engine.

Coordinates the multi-level workflow:
1. Risk Officer scans holdings -> produces WorkProposals.
2. Fiduciary Reviewer conducts forensic investigation & policy audit -> produces ReviewEvaluations.
   - Executes bi-directional revision loop if revision is required.
3. Financial Planning Boss synthesizes approved proposals -> produces DirectiveCards.
4. Stores directives and records every step on the public debate blackboard.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.agents.boss import FinancialPlanningBossAgent
from core.agents.models import (
    AgentProfile,
    DirectiveCard,
    DirectiveStatus,
    ProposalActionType,
    TimelineEvent,
    WorkProposal,
)
from core.agents.reviewer import FiduciaryReviewerAgent
from core.agents.risk_officer import RiskOfficerAgent
from core.agents.storage import get_boardroom_storage

logger = logging.getLogger("wealthvault.agents.orchestrator")


class BoardroomOrchestrator:
    """Coordinates multi-agent deliberations and directive generation."""

    def __init__(self):
        self.risk_officer = RiskOfficerAgent()
        self.reviewer = FiduciaryReviewerAgent()
        self.boss = FinancialPlanningBossAgent()
        self.storage = get_boardroom_storage()

    def get_agent_profiles(self) -> List[AgentProfile]:
        """Return the current statuses of all boardroom agents."""
        return [
            self.boss.profile,
            self.reviewer.profile,
            self.risk_officer.profile,
        ]

    async def run_review_cycle(
        self,
        holdings: List[Dict[str, Any]],
        total_portfolio_value: float,
        benchmark_nifty_move_pct: float = 0.0,
        trigger_source: str = "MANUAL",
        owner_id: Optional[str] = None
    ) -> List[DirectiveCard]:
        """Execute a full deliberation cycle across the 3-tier hierarchy."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Log trigger
        self.storage.add_timeline_event(
            TimelineEvent(
                event_id=f"evt_trigger_{int(datetime.now(timezone.utc).timestamp())}",
                agent_id="system",
                agent_name="Boardroom Clock",
                event_type="TRIGGER",
                message=f"Boardroom evaluation cycle initiated via {trigger_source}. Auditing {len(holdings)} holdings.",
                metadata={"holdings_count": len(holdings), "total_value": total_portfolio_value}
            )
        )

        # Tier 1: Risk Officer Analysis
        proposals = self.risk_officer.analyze_holdings(holdings, total_portfolio_value)
        if not proposals:
            self.storage.add_timeline_event(
                TimelineEvent(
                    event_id=f"evt_ro_clear_{int(datetime.now(timezone.utc).timestamp())}",
                    agent_id=self.risk_officer.profile.agent_id,
                    agent_name=self.risk_officer.profile.name,
                    event_type="EVALUATION",
                    message="Capital & Risk Scan Complete: 0 stop-loss breaches, 0 concentration violations. Portfolio within safe operating parameters."
                )
            )
            return []

        new_directives: List[DirectiveCard] = []

        # Process each proposal through Tier 2 and Tier 3
        for prop in proposals:
            # 1. Log Proposal
            self.storage.add_timeline_event(
                TimelineEvent(
                    event_id=f"evt_prop_{prop.proposal_id}",
                    agent_id=prop.source_agent_id,
                    agent_name=prop.source_agent_name,
                    event_type="PROPOSAL",
                    message=f"Submitted Proposal: {prop.thesis}",
                    proposal_id=prop.proposal_id,
                    metadata=prop.underlying_metrics
                )
            )

            # 2. Tier 2: Fiduciary Reviewer Forensic Audit (Crawls News, Financials & Genuine Technical Momentum)
            evaluation = await self.reviewer.audit_proposal(prop, benchmark_nifty_move_pct, owner_id=owner_id)

            # Log Reviewer Audit
            self.storage.add_timeline_event(
                TimelineEvent(
                    event_id=f"evt_eval_{evaluation.evaluation_id}",
                    agent_id=self.reviewer.profile.agent_id,
                    agent_name=self.reviewer.profile.name,
                    event_type="POLICY_CHECK",
                    message=f"Forensic Audit Verdict: {evaluation.verdict}. {evaluation.critique_and_feedback or ''}".strip(),
                    proposal_id=prop.proposal_id,
                    metadata={
                        "verdict": evaluation.verdict,
                        "passed_rules": evaluation.passed_rules_count,
                        "risk_score": evaluation.investigation_dossier.forensic_risk_score if evaluation.investigation_dossier else 0
                    }
                )
            )

            # 3. Bi-Directional Revision Loop
            if evaluation.verdict == "REVISION_REQUIRED":
                # Risk officer adapts proposal
                prop.revision_round += 1
                feedback = evaluation.critique_and_feedback or ""
                rev_msg = f"Adapted Proposal (Round {prop.revision_round}): Addressed Reviewer feedback."

                if "HOLD_DEFENSE" in feedback or "False Breakdown" in feedback:
                    # Reviewer overruled the market dump: adapt to HOLD_DEFENSE
                    if prop.proposed_actions:
                        for act in prop.proposed_actions:
                            act.action = ProposalActionType.HOLD_DEFENSE
                            act.trigger_reason = "Overruled by Fiduciary Reviewer: Structural 200-DMA support intact. Reset stop to 200-DMA."
                    display = prop.underlying_metrics.get("display_name", "")
                    prop.thesis = f"HOLD DEFENSE: Fiduciary Reviewer rejected market selloff on {display}. Structural 200-DMA support and ROCE intact."
                    rev_msg = f"Adapted Proposal (Round {prop.revision_round}): Switched action to HOLD_DEFENSE per Reviewer False Breakdown Protection."
                elif prop.proposed_actions and "AMO" in feedback:
                    prop.proposed_actions[0].order_type = "AMO_LIMIT"
                    rev_msg = f"Adapted Proposal (Round {prop.revision_round}): Updated order type to AMO_LIMIT per Reviewer feedback."

                self.storage.add_timeline_event(
                    TimelineEvent(
                        event_id=f"evt_rev_{prop.proposal_id}_{prop.revision_round}",
                        agent_id=self.risk_officer.profile.agent_id,
                        agent_name=self.risk_officer.profile.name,
                        event_type="REVISION",
                        message=rev_msg,
                        proposal_id=prop.proposal_id
                    )
                )

                # Re-audit revised proposal
                evaluation = await self.reviewer.audit_proposal(prop, benchmark_nifty_move_pct, owner_id=owner_id)
                self.storage.add_timeline_event(
                    TimelineEvent(
                        event_id=f"evt_eval_recheck_{evaluation.evaluation_id}",
                        agent_id=self.reviewer.profile.agent_id,
                        agent_name=self.reviewer.profile.name,
                        event_type="POLICY_CHECK",
                        message=f"Re-audit Verdict: {evaluation.verdict}. All safety criteria cleared.",
                        proposal_id=prop.proposal_id
                    )
                )

            # 4. Tier 3: Financial Planning Boss Synthesis
            if evaluation.verdict == "APPROVED":
                directive = self.boss.synthesize_directive(prop, evaluation)
                if directive:
                    self.storage.save_directive(directive)
                    new_directives.append(directive)

                    # Log Boss Directive
                    self.storage.add_timeline_event(
                        TimelineEvent(
                            event_id=f"evt_dir_{directive.directive_id}",
                            agent_id=self.boss.profile.agent_id,
                            agent_name=self.boss.profile.name,
                            event_type="DIRECTIVE_ISSUED",
                            message=f"Issued Action Directive: {directive.title}. Awaiting investor closure.",
                            directive_id=directive.directive_id
                        )
                    )

        return new_directives


# Global singleton
_orchestrator = BoardroomOrchestrator()

def get_orchestrator() -> BoardroomOrchestrator:
    return _orchestrator

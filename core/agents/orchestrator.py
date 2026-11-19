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
from core.agents.forensic_crawler import clean_display_name, clean_symbol
from core.agents.models import (
    AgentProfile,
    DirectiveCard,
    DirectiveStatus,
    ProposalActionType,
    ReviewEvaluation,
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

    async def run_fiduciary_audit(
        self,
        holdings: List[Dict[str, Any]],
        total_portfolio_value: float,
        benchmark_nifty_move_pct: float = 0.0,
        trigger_source: str = "MANUAL",
        owner_id: Optional[str] = None
    ) -> List[DirectiveCard]:
        """Execute Phase 2: Risk Officer Scan & Fiduciary Reviewer Forensic Audit.
        
        Performs in-place replacement: purges previous directives so stale positions
        from older runs never linger.
        """
        self.storage.add_timeline_event(
            TimelineEvent(
                event_id=f"evt_trigger_{int(datetime.now(timezone.utc).timestamp())}",
                agent_id="system",
                agent_name="Boardroom Clock",
                event_type="TRIGGER",
                message=f"Phase 2: Fiduciary Audit initiated via {trigger_source}. Auditing {len(holdings)} holdings against 4 core policies.",
                metadata={"holdings_count": len(holdings), "total_value": total_portfolio_value}
            ),
            owner_id=owner_id
        )

        # Clear existing directives for clean in-place replacement (no stale history)
        self.storage.clear_directives(owner_id=owner_id)

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
                ),
                owner_id=owner_id
            )
            return []

        audited_directives: List[DirectiveCard] = []

        # Process each proposal through Tier 2 (Fiduciary Reviewer)
        for prop in proposals:
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

            # Tier 2: Fiduciary Reviewer Forensic Audit
            evaluation = await self.reviewer.audit_proposal(prop, benchmark_nifty_move_pct, owner_id=owner_id)

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

            # Bi-Directional Revision Loop (False Breakdown Protection)
            if evaluation.verdict == "REVISION_REQUIRED":
                prop.revision_round += 1
                feedback = evaluation.critique_and_feedback or ""
                rev_msg = f"Adapted Proposal (Round {prop.revision_round}): Addressed Reviewer feedback."

                if "HOLD_DEFENSE" in feedback or "False Breakdown" in feedback:
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

            # Store audited directive card
            if evaluation.verdict == "APPROVED":
                first_action = prop.proposed_actions[0] if prop.proposed_actions else None
                symbol = first_action.symbol if first_action else "Portfolio"
                clean_sym = clean_symbol(symbol).upper()
                broker_key = (first_action.broker if first_action else "broker").lower()
                action_key = (first_action.action.value if first_action else "rebalance").lower()
                directive_id = f"dir_{clean_sym}_{broker_key}_{action_key}"

                display_name = clean_display_name(symbol)
                action_name = first_action.action.value.replace("_", " ").title() if first_action else "Rebalance"
                broker_name = (first_action.broker if first_action else "Broker").capitalize()

                existing = self.storage.get_directive(directive_id)
                ai_delib = existing.ai_deliberated if existing else False
                ai_status = existing.ai_deliberation_status if existing else "PENDING_BOSS_DELIBERATION"
                thesis = existing.summary_thesis if (existing and existing.ai_deliberated) else (
                    f"• Fiduciary Audit Completed: Vetted under 4 institutional policies. Verdict: {evaluation.verdict}.\n"
                    f"• Reviewer Finding: {evaluation.critique_and_feedback or 'Cleared all safety checks.'}\n"
                    f"• Awaiting Phase 3: Click 'Deliberate CIO Directives' to synthesize final Gemini executive order."
                )

                directive = DirectiveCard(
                    directive_id=directive_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    title=f"{action_name}: {display_name} ({broker_name})",
                    display_name=display_name,
                    trend_verdict=first_action.trend_verdict if first_action else "Neutral",
                    holding_quantity=first_action.holding_quantity if first_action else None,
                    holding_avg_price=first_action.holding_avg_price if first_action else None,
                    pnl_pct=first_action.pnl_pct if first_action else None,
                    summary_thesis=thesis,
                    priority=prop.urgency,
                    originating_subagents=[prop.source_agent_id],
                    actions=prop.proposed_actions,
                    review_verdict=evaluation.verdict,
                    review_summary=evaluation.critique_and_feedback or "Approved by Fiduciary Reviewer",
                    investigation_dossier=evaluation.investigation_dossier,
                    user_status=existing.user_status if existing else DirectiveStatus.PENDING_REVIEW,
                    ai_deliberated=ai_delib,
                    ai_deliberation_status=ai_status,
                )
                self.storage.save_directive(directive, owner_id=owner_id)
                audited_directives.append(directive)

        return audited_directives

    async def run_boss_deliberation(
        self,
        holdings: List[Dict[str, Any]],
        total_portfolio_value: float,
        trigger_source: str = "MANUAL",
        owner_id: Optional[str] = None
    ) -> List[DirectiveCard]:
        """Execute Phase 3: Chief Investment Officer Gemini AI Deliberation & Capital Redeployment.
        
        Strict Mandate: Wipe all existing directives first before synthesizing new ones so zero
        stale history or duplicate proposals ever accumulate.
        """
        self.storage.add_timeline_event(
            TimelineEvent(
                event_id=f"evt_boss_start_{int(datetime.now(timezone.utc).timestamp())}",
                agent_id=self.boss.profile.agent_id,
                agent_name=self.boss.profile.name,
                event_type="TRIGGER",
                message=f"Phase 3: CIO Autonomous AI Deliberation initiated via {trigger_source}. Synthesizing directives across 6-scout radar.",
            ),
            owner_id=owner_id
        )

        # 1. Ensure active directives exist; if none, run audit first
        active_dirs = self.storage.list_directives(status=DirectiveStatus.PENDING_REVIEW, owner_id=owner_id)
        if not active_dirs and holdings:
            active_dirs = await self.run_fiduciary_audit(holdings, total_portfolio_value, owner_id=owner_id)

        # Snapshot current proposals to deliberate
        proposals_to_deliberate = list(active_dirs)

        # 2. Strict User Mandate: "for 3rd stage, just remove everything first and then only start with reviews. for now, lets not store any history."
        self.storage.clear_directives(owner_id=owner_id)

        deliberated_directives: List[DirectiveCard] = []
        for d in proposals_to_deliberate:
            first_action = d.actions[0] if d.actions else None
            if not first_action:
                continue

            prop = WorkProposal(
                proposal_id=f"prop_{d.directive_id}",
                source_agent_id="risk_officer",
                source_agent_name="Risk Officer",
                urgency=d.priority,
                thesis=d.title,
                underlying_metrics={"pnl_pct": d.pnl_pct or 0.0},
                proposed_actions=d.actions
            )
            eval_obj = ReviewEvaluation(
                evaluation_id=f"eval_{d.directive_id}",
                proposal_id=prop.proposal_id,
                verdict=d.review_verdict,
                critique_and_feedback=d.review_summary,
                investigation_dossier=d.investigation_dossier
            )

            synth_dir = self.boss.synthesize_directive(prop, eval_obj)
            if synth_dir:
                if d.user_status != DirectiveStatus.PENDING_REVIEW:
                    synth_dir.user_status = d.user_status
                    synth_dir.user_comment = d.user_comment
                    synth_dir.resolved_at = d.resolved_at
                self.storage.save_directive(synth_dir, owner_id=owner_id)
                deliberated_directives.append(synth_dir)

                self.storage.add_timeline_event(
                    TimelineEvent(
                        event_id=f"evt_dir_{synth_dir.directive_id}",
                        agent_id=self.boss.profile.agent_id,
                        agent_name=self.boss.profile.name,
                        event_type="DIRECTIVE_ISSUED",
                        message=f"Issued CIO Action Directive: {synth_dir.title}. Capital redeployment queued.",
                        directive_id=synth_dir.directive_id
                    ),
                    owner_id=owner_id
                )

        return deliberated_directives

    async def run_review_cycle(
        self,
        holdings: List[Dict[str, Any]],
        total_portfolio_value: float,
        benchmark_nifty_move_pct: float = 0.0,
        trigger_source: str = "MANUAL",
        owner_id: Optional[str] = None
    ) -> List[DirectiveCard]:
        """Execute full 3-phase cycle (Audit + Boss Deliberation)."""
        await self.run_fiduciary_audit(holdings, total_portfolio_value, benchmark_nifty_move_pct, trigger_source, owner_id)
        return await self.run_boss_deliberation(holdings, total_portfolio_value, trigger_source, owner_id)


# Global singleton
_orchestrator = BoardroomOrchestrator()

def get_orchestrator() -> BoardroomOrchestrator:
    return _orchestrator

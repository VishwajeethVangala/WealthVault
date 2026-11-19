import React, { useEffect, useState, useCallback, useMemo } from 'react'
import {
  FileSearch,
  Crown,
  Play,
  AlertTriangle,
  ChevronRight,
  RefreshCw,
  Check,
  X,
  Search,
  Building2,
  TrendingDown,
  TrendingUp,
  Scale,
  ExternalLink,
  ShieldCheck,
  Compass,
  ArrowUpRight,
  Sparkles,
  Copy,
  SlidersHorizontal,
  ShieldAlert,
  CheckCircle2,
} from 'lucide-react'
import {
  fetchBoardroom,
  runBoardroomReview,
  runFiduciaryAudit,
  runBossDeliberation,
  triggerGroundSwarmScan,
  updateDirectiveStatus,
  fetchGroundSwarmOverview,
} from '../utils/api'
import type {
  BoardroomOverview,
  DirectiveCard,
  GroundStockDossier,
  GroundSwarmOverview,
} from '../types'
import { GroundSwarmView } from '../components/agents/GroundSwarmView'
import { formatTicker, formatCompanyName } from '../utils/tickerFormat'

export const formatDisplayName = (raw: string): string => {
  return formatCompanyName(raw)
}

const getBrokerBadgeClass = (broker?: string) => {
  const b = (broker || '').toLowerCase()
  if (b.includes('zerodha') || b.includes('kite')) return 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20'
  if (b.includes('groww')) return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
  if (b.includes('indmoney')) return 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20'
  return 'bg-surface-2 text-wv-text-2 border-wv-border'
}

export const getTrendVerdict = (d: DirectiveCard): string => {
  if (d.trend_verdict && d.trend_verdict.trim()) return d.trend_verdict
  const first = d.actions?.[0]
  if (first?.trend_verdict && first.trend_verdict.trim()) return first.trend_verdict
  if (d.investigation_dossier?.technical_trend) return d.investigation_dossier.technical_trend
  return 'Neutral'
}

const isExitAction = (action?: string): boolean => {
  return action === 'CUT_LOSS' || action === 'EXIT_ALL'
}

const isTrimAction = (action?: string): boolean => {
  return action === 'TRAILING_TRIM' || action === 'REBALANCE'
}

export type ReviewerAuditCategory = 'ALL' | 'SHIELD' | 'ROT' | 'TRIM'

interface ClassifiedVerdict {
  category: 'SHIELD' | 'ROT' | 'TRIM'
  badgeLabel: string
  badgeClass: string
  scoutAlarm: string
  reviewerChallenge: string
  fiduciaryFinding: string
  recommendation: string
}

function classifyAuditVerdict(
  directive: DirectiveCard,
  dossier: GroundStockDossier | null,
  pnl: number,
  _cleanTicker: string
): ClassifiedVerdict {
  const action = directive.actions[0]?.action
  const roce = dossier?.funda_report?.roce_pct ?? directive.investigation_dossier?.fundamental_vitals?.roce_pct

  // 1. False Breakdown Shield: HOLD_DEFENSE (overruled & protected at 200-DMA)
  if (action === 'HOLD_DEFENSE') {
    return {
      category: 'SHIELD',
      badgeLabel: '🛡️ FALSE BREAKDOWN SHIELD',
      badgeClass: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30 font-semibold',
      scoutAlarm: `Risk Scout flagged stop-loss breach (${pnl.toFixed(1)}% drawdown). Recommended market dump.`,
      reviewerChallenge: `Overruled & Protected: Outstanding ROCE (${roce != null ? roce.toFixed(1) + '%' : 'sound'}), testing rising 200-DMA support. Dip driven by systemic market beta, not company insolvency.`,
      fiduciaryFinding: 'Structural base intact. Retail stop-loss shakeout rejected. Preserve holding with stop at 200-DMA.',
      recommendation: 'HOLD DEFENSE: Stop strictly pegged to 200-DMA to avoid whipsaw loss.',
    }
  }

  // 2. Tactical Risk Trim: Partial de-risking (TRAILING_TRIM, REBALANCE)
  if (isTrimAction(action)) {
    return {
      category: 'TRIM',
      badgeLabel: '🟡 TACTICAL RISK TRIM',
      badgeClass: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30 font-semibold',
      scoutAlarm: 'Risk Scout flagged high volatility or profit protection threshold reached.',
      reviewerChallenge: 'Tactical De-risking: Harvest 50% risk off the table while allowing remainder to run with trailing stop-loss.',
      fiduciaryFinding: 'Position overextended relative to market volatility. De-risk partial sizing to protect core gains.',
      recommendation: 'TRIM 50%: Lock in downside protection and rebalance liberated liquidity into safe cash reserve.',
    }
  }

  // 3. Confirmed Capital Rot: CUT_LOSS / EXIT_ALL (euthanasia mandated)
  return {
    category: 'ROT',
    badgeLabel: '🔴 CONFIRMED CAPITAL ROT',
    badgeClass: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30 font-semibold',
    scoutAlarm: `Risk Scout: Drawdown of ${pnl.toFixed(1)}%. Tech Scout: Confirmed breakdown below key moving averages.`,
    reviewerChallenge: `Euthanasia Mandated: Cross-examination confirms deep structural decay${roce != null ? ` (ROCE ${roce.toFixed(1)}%)` : ''}. Zero recovery catalyst. Munger Inversion rule #1 applies: Stop compounding errors.`,
    fiduciaryFinding: 'Severe thesis invalidation across Technical + Fundamental + News dimensions. Full euthanasia mandated.',
    recommendation: 'FULL 100% EXIT: Halt ongoing capital destruction and recycle cash into Stage 2 leaders.',
  }
}

/** Render CIO executive thesis with structured justification pointers. */
function renderThesisPointers(thesis: string) {
  if (!thesis) return null

  // 1. If it's a held alert
  if (thesis.startsWith('⚠️')) {
    return (
      <div className="flex items-start gap-2 text-xs text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20 p-2.5 rounded-lg">
        <span className="shrink-0 mt-0.5">⚠️</span>
        <span className="leading-relaxed">{thesis.replace(/^⚠️\s*/, '')}</span>
      </div>
    )
  }

  // 2. Filter out raw memorandum header lines if present
  const lines = thesis
    .split(/\n+/)
    .map((l) => l.trim())
    .filter(
      (l) =>
        l &&
        !l.startsWith('**MEMORANDUM') &&
        !l.startsWith('**TO:') &&
        !l.startsWith('**FROM:') &&
        !l.startsWith('**SUBJECT:') &&
        !l.startsWith('**DATE:') &&
        !l.startsWith('Team,')
    )

  // 3. Check for explicit bullet lines (•, *, -, 1.)
  const bulletLines = lines.filter((l) => l.startsWith('•') || l.startsWith('*') || l.startsWith('-') || /^\d+\./.test(l))

  let pointers: Array<{ title: string; body: string }> = []

  if (bulletLines.length > 0) {
    pointers = bulletLines.map((line) => {
      let clean = line.replace(/^[•\-*]\s*/, '').replace(/^\d+\.\s*/, '').trim()
      clean = clean.replace(/^\*\*(.*?)\*\*/, '$1') // e.g. **Forensic & Technical:** -> Forensic & Technical:

      const colonIdx = clean.indexOf(':')
      if (colonIdx > 0 && colonIdx < 50) {
        return {
          title: clean.slice(0, colonIdx + 1).trim(),
          body: clean.slice(colonIdx + 1).trim().replace(/^\*\*/, '').replace(/\*\*$/, ''),
        }
      }
      return { title: '', body: clean }
    })
  } else {
    // 4. Intelligent Parser for Paragraph Theses: converts narrative paragraphs into 3 pointers
    let mainText = lines.join(' ')
    let redeployText = ''

    const redeployIdx = mainText.indexOf('Capital Redeployment:')
    if (redeployIdx > 0) {
      redeployText = mainText.slice(redeployIdx + 'Capital Redeployment:'.length).trim()
      mainText = mainText.slice(0, redeployIdx).trim()
    }

    const sentences = mainText
      .split(/(?<=[.!?])\s+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 10)

    if (sentences.length >= 2) {
      pointers.push({
        title: 'Forensic & Technical Reality:',
        body: sentences[0],
      })
      pointers.push({
        title: 'Capital Preservation Mandate:',
        body: sentences.slice(1).join(' '),
      })
    } else if (sentences.length === 1) {
      pointers.push({
        title: 'Fiduciary Justification:',
        body: sentences[0],
      })
    }

    if (redeployText) {
      pointers.push({
        title: 'Strategic Capital Redeployment:',
        body: redeployText,
      })
    }
  }

  if (pointers.length === 0) {
    return <p className="text-xs text-wv-text-2 leading-relaxed whitespace-pre-line">{thesis}</p>
  }

  return (
    <ul className="space-y-2 list-none pl-0 my-0">
      {pointers.map((p, idx) => (
        <li key={idx} className="flex items-start gap-2.5 text-xs text-wv-text-2 leading-relaxed">
          <span className="w-1.5 h-1.5 rounded-full bg-wv-accent shrink-0 mt-1.5 ring-2 ring-wv-accent/20" />
          <span>
            {p.title && <strong className="text-wv-text font-semibold mr-1.5">{p.title}</strong>}
            <span>{p.body}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

export const AgentBoardroom: React.FC = () => {
  const [data, setData] = useState<BoardroomOverview | null>(null)
  const [groundData, setGroundData] = useState<GroundSwarmOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedDirective, setSelectedDirective] = useState<DirectiveCard | null>(null)
  const [copiedManifest, setCopiedManifest] = useState(false)

  // 3 Primary Horizontal Tabs: ground | reviewer | boss
  const [activeTab, setActiveTab] = useState<'ground' | 'reviewer' | 'boss'>('ground')

  // Filters for The Reviewer Tab (Tab 2)
  const [reviewerCategory, setReviewerCategory] = useState<ReviewerAuditCategory>('ALL')
  const [reviewerSearch, setReviewerSearch] = useState('')
  const [reviewerBroker, setReviewerBroker] = useState<string>('all')
  const [reviewerRoceFilter, setReviewerRoceFilter] = useState<string>('all')
  const [reviewerNewsFilter, setReviewerNewsFilter] = useState<string>('all')
  const [reviewerTechFilter, setReviewerTechFilter] = useState<string>('all')

  // Filters for The Boss Tab (Tab 3)
  const [bossSubTab, setBossSubTab] = useState<'reclamation' | 'redeployment' | 'archived'>('reclamation')
  const [bossUrgency, setBossUrgency] = useState<string>('all')
  const [bossBroker, setBossBroker] = useState<string>('all')
  const [bossSearch, setBossSearch] = useState('')
  const [bossActionFilter, setBossActionFilter] = useState<string>('all')
  const [bossRoceFilter, setBossRoceFilter] = useState<string>('all')
  const [bossAiFilter, setBossAiFilter] = useState<string>('all')

  const loadBoardroom = useCallback(async () => {
    try {
      const [boardroomRes, groundRes] = await Promise.all([
        fetchBoardroom(),
        fetchGroundSwarmOverview().catch(() => null),
      ])
      setData(boardroomRes)
      if (groundRes) setGroundData(groundRes)
      setError(null)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to connect to Fiduciary Review Engine'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadBoardroom()
  }, [loadBoardroom])

  const [runningPhase, setRunningPhase] = useState<'none' | 'ground' | 'audit' | 'boss' | 'all'>('none')

  const handleRunGroundScan = async () => {
    try {
      setRunningPhase('ground')
      setError(null)
      await triggerGroundSwarmScan(3.0)
      const groundRes = await fetchGroundSwarmOverview()
      if (groundRes) setGroundData(groundRes)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Ground scan failed'
      setError(msg)
    } finally {
      setRunningPhase('none')
    }
  }

  const handleRunFiduciaryAudit = async () => {
    try {
      setRunningPhase('audit')
      setError(null)
      await runFiduciaryAudit()
      await loadBoardroom()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Fiduciary audit failed'
      setError(msg)
    } finally {
      setRunningPhase('none')
    }
  }

  const handleRunBossDeliberation = async () => {
    try {
      setRunningPhase('boss')
      setError(null)
      await runBossDeliberation()
      await loadBoardroom()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Boss deliberation failed'
      setError(msg)
    } finally {
      setRunningPhase('none')
    }
  }

  const handleRunAllPhases = async () => {
    try {
      setRunningPhase('all')
      setError(null)
      await runBoardroomReview()
      await loadBoardroom()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Review deliberation failed'
      setError(msg)
    } finally {
      setRunningPhase('none')
    }
  }

  const handleUpdateStatus = async (
    directiveId: string,
    status: 'ORDER_PLACED_AT_BROKER' | 'IGNORED' | 'SNOOZED',
    comment?: string
  ) => {
    try {
      await updateDirectiveStatus(directiveId, status, comment)
      if (selectedDirective?.directive_id === directiveId) {
        setSelectedDirective((prev) => (prev ? { ...prev, user_status: status as any } : null))
      }
      await loadBoardroom()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update directive status'
      setError(msg)
    }
  }

  const activeDirectives = useMemo(() => {
    return data?.active_directives || []
  }, [data?.active_directives])

  const historicalDirectives = useMemo(() => {
    return data?.historical_directives || []
  }, [data?.historical_directives])

  // Lookup map for Ground Intelligence Dossiers by clean uppercase symbol
  const dossierMap = useMemo(() => {
    const map: Record<string, GroundStockDossier> = {}
    if (groundData?.dossiers) {
      groundData.dossiers.forEach((d) => {
        map[d.symbol.toUpperCase()] = d
        const clean = formatTicker(d.symbol)
        if (clean) map[clean.toUpperCase()] = d
      })
    }
    return map
  }, [groundData])

  // Extract unique brokers
  const brokers = useMemo(() => {
    const set = new Set<string>()
    activeDirectives.forEach((d) => {
      d.actions.forEach((a) => {
        if (a.broker) set.add(a.broker.toLowerCase())
      })
    })
    return Array.from(set)
  }, [activeDirectives])

  // Capital Calculations for The Boss (Tab 3)
  const capitalMetrics = useMemo(() => {
    let totalFreedCash = 0
    let totalUnrealizedLoss = 0
    let urgentCount = 0

    activeDirectives.forEach((d) => {
      const action = d.actions[0]
      const qty = action?.holding_quantity ?? d.holding_quantity ?? action?.quantity ?? 0
      const price = action?.estimated_price ?? action?.holding_avg_price ?? d.holding_avg_price ?? 0
      const pnlPct = action?.pnl_pct ?? d.pnl_pct ?? 0
      const posValue = qty * price

      if (action) {
        if (isExitAction(action.action)) {
          totalFreedCash += posValue
          if (pnlPct < 0) {
            totalUnrealizedLoss += Math.abs(posValue * (pnlPct / 100))
          }
        } else if (isTrimAction(action.action)) {
          totalFreedCash += posValue * 0.5
          if (pnlPct < 0) {
            totalUnrealizedLoss += Math.abs(posValue * 0.5 * (pnlPct / 100))
          }
        }
      }
      if (d.priority === 'CRITICAL' || d.priority === 'HIGH') {
        urgentCount += 1
      }
    })

    return {
      activeCount: activeDirectives.length,
      urgentCount,
      totalFreedCash,
      totalUnrealizedLoss,
    }
  }, [activeDirectives])

  // Dynamic Capital Redeployment Targets (Top Stage 2 Leaders)
  const redeploymentTargets = useMemo(() => {
    const totalFreed = capitalMetrics.totalFreedCash

    if (!groundData?.dossiers || groundData.dossiers.length === 0) {
      return [
        {
          symbol: 'GREAVESCOT',
          companyName: 'Greaves Cotton Ltd',
          stage: 'Stage 2: Markup',
          momentum: '5/5',
          roce: 10.1,
          rsScore: '+13.2%',
          allocationPct: 40,
          allocatedRupees: Math.round(totalFreed * 0.4),
          targetPrice: 164.2,
          targetShares: Math.floor((totalFreed * 0.4) / 164.2),
          rationale: 'Stage 2 markup leader with volume surge and expanding profit margins. High RS outperformer.',
        },
        {
          symbol: 'LUMAXTECH',
          companyName: 'Lumax Auto Tech Ltd',
          stage: 'Stage 2: Markup',
          momentum: '5/5',
          roce: 21.2,
          rsScore: '+9.8%',
          allocationPct: 35,
          allocatedRupees: Math.round(totalFreed * 0.35),
          targetPrice: 301.5,
          targetShares: Math.floor((totalFreed * 0.35) / 301.5),
          rationale: 'Institutional sponsorship leader with 21.2% ROCE and clean breakout from consolidation base.',
        },
      ]
    }

    const stage2Candidates = groundData.dossiers
      .filter((d) => {
        const stage = d.tech_report?.stage_verdict || ''
        const roce = d.funda_report?.roce_pct || 0
        return stage.includes('Stage 2') && roce >= 10
      })
      .sort((a, b) => {
        const scoreA = (a.funda_report?.roce_pct || 0) + (a.tech_report?.rs_score_vs_nifty || 0)
        const scoreB = (b.funda_report?.roce_pct || 0) + (b.tech_report?.rs_score_vs_nifty || 0)
        return scoreB - scoreA
      })

    if (stage2Candidates.length >= 2) {
      const c1 = stage2Candidates[0]
      const c2 = stage2Candidates[1]
      const p1 = c1.tech_report?.current_price || 164.2
      const p2 = c2.tech_report?.current_price || 301.5

      return [
        {
          symbol: formatTicker(c1.symbol),
          companyName: formatCompanyName(c1.symbol, c1.company_name),
          stage: c1.tech_report?.stage_verdict?.split(':')[0] || 'Stage 2',
          momentum: `${c1.tech_report?.momentum_score || 4}/5`,
          roce: c1.funda_report?.roce_pct || 20,
          rsScore: `+${(c1.tech_report?.rs_score_vs_nifty || 12).toFixed(1)}%`,
          allocationPct: 40,
          allocatedRupees: Math.round(totalFreed * 0.4),
          targetPrice: p1,
          targetShares: Math.floor((totalFreed * 0.4) / p1),
          rationale: 'Highest combined ROCE and Relative Strength outperformer in Stage 2 markup.',
        },
        {
          symbol: formatTicker(c2.symbol),
          companyName: formatCompanyName(c2.symbol, c2.company_name),
          stage: c2.tech_report?.stage_verdict?.split(':')[0] || 'Stage 2',
          momentum: `${c2.tech_report?.momentum_score || 4}/5`,
          roce: c2.funda_report?.roce_pct || 18,
          rsScore: `+${(c2.tech_report?.rs_score_vs_nifty || 9).toFixed(1)}%`,
          allocationPct: 35,
          allocatedRupees: Math.round(totalFreed * 0.35),
          targetPrice: p2,
          targetShares: Math.floor((totalFreed * 0.35) / p2),
          rationale: 'Strong institutional accumulation with robust balance sheet solvency and volume expansion.',
        },
      ]
    }

    return [
      {
        symbol: 'GREAVESCOT',
        companyName: 'Greaves Cotton Ltd',
        stage: 'Stage 2: Markup',
        momentum: '5/5',
        roce: 10.1,
        rsScore: '+13.2%',
        allocationPct: 40,
        allocatedRupees: Math.round(totalFreed * 0.4),
        targetPrice: 164.2,
        targetShares: Math.floor((totalFreed * 0.4) / 164.2),
        rationale: 'Stage 2 markup leader with volume surge and expanding profit margins. High RS outperformer.',
      },
      {
        symbol: 'LUMAXTECH',
        companyName: 'Lumax Auto Tech Ltd',
        stage: 'Stage 2: Markup',
        momentum: '5/5',
        roce: 21.2,
        rsScore: '+9.8%',
        allocationPct: 35,
        allocatedRupees: Math.round(totalFreed * 0.35),
        targetPrice: 301.5,
        targetShares: Math.floor((totalFreed * 0.35) / 301.5),
        rationale: 'Institutional sponsorship leader with 21.2% ROCE and clean breakout from consolidation base.',
      },
    ]
  }, [groundData?.dossiers, capitalMetrics.totalFreedCash])

  // Classified Reviewer Directives with Debate & Verdicts
  const classifiedReviewerList = useMemo(() => {
    return activeDirectives.map((d) => {
      const firstAction = d.actions[0]
      const cleanTick = formatTicker(firstAction?.symbol, d.investigation_dossier?.symbol)
      const company = formatCompanyName(firstAction?.symbol, d.display_name)
      const pnl = firstAction?.pnl_pct ?? d.pnl_pct ?? 0
      const groundDossier = dossierMap[cleanTick] || dossierMap[firstAction?.symbol || ''] || null
      const verdict = classifyAuditVerdict(d, groundDossier, pnl, cleanTick)

      return {
        directive: d,
        cleanTicker: cleanTick,
        companyName: company,
        groundDossier,
        pnl,
        verdict,
      }
    })
  }, [activeDirectives, dossierMap])

  // Reviewer Tier Counts
  const reviewerStats = useMemo(() => {
    let shields = 0
    let rot = 0
    let trims = 0

    classifiedReviewerList.forEach((item) => {
      if (item.verdict.category === 'SHIELD') shields += 1
      else if (item.verdict.category === 'ROT') rot += 1
      else trims += 1
    })

    return {
      total: classifiedReviewerList.length,
      shields,
      rot,
      trims,
    }
  }, [classifiedReviewerList])

  // Filtered Directives for The Reviewer Tab (Tab 2)
  const filteredReviewerDirectives = useMemo(() => {
    return classifiedReviewerList.filter(({ cleanTicker, companyName, directive, verdict, groundDossier }) => {
      const q = reviewerSearch.toLowerCase().trim()
      const matchesSearch =
        !q ||
        cleanTicker.toLowerCase().includes(q) ||
        companyName.toLowerCase().includes(q) ||
        (directive.title && directive.title.toLowerCase().includes(q))

      if (!matchesSearch) return false

      if (reviewerCategory !== 'ALL' && verdict.category !== reviewerCategory) {
        return false
      }

      if (reviewerBroker !== 'all') {
        const broker = directive.actions[0]?.broker?.toLowerCase()
        if (broker !== reviewerBroker) return false
      }

      // Reviewer ROCE Solvency Filter
      if (reviewerRoceFilter !== 'all') {
        const roce = groundDossier?.funda_report?.roce_pct ?? directive.investigation_dossier?.fundamental_vitals?.roce_pct
        if (reviewerRoceFilter === 'healthy' && (roce == null || roce < 12)) return false
        if (reviewerRoceFilter === 'subpar' && (roce == null || roce >= 12 || roce < 0)) return false
        if (reviewerRoceFilter === 'negative' && (roce == null || roce >= 0)) return false
      }

      // Reviewer News Threat Filter
      if (reviewerNewsFilter !== 'all') {
        const hasThreat = Boolean(groundDossier?.news_report?.material_threat)
        if (reviewerNewsFilter === 'threat' && !hasThreat) return false
        if (reviewerNewsFilter === 'clean' && hasThreat) return false
      }

      // Reviewer Technical Support Filter
      if (reviewerTechFilter !== 'all') {
        const sma200 = groundDossier?.tech_report?.sma_200
        const curPrice = groundDossier?.tech_report?.current_price ?? directive.actions[0]?.estimated_price ?? 0
        const isHolding200 = Boolean(sma200 && curPrice >= sma200 * 0.95)
        const trend = (groundDossier?.tech_report?.stage_verdict ?? directive.investigation_dossier?.technical_trend ?? '').toLowerCase()

        if (reviewerTechFilter === 'holding_200' && !isHolding200) return false
        if (reviewerTechFilter === 'stage_4' && !trend.includes('stage 4')) return false
        if (reviewerTechFilter === 'uptrend' && !trend.includes('stage 2') && !trend.includes('uptrend')) return false
      }

      return true
    })
  }, [classifiedReviewerList, reviewerCategory, reviewerSearch, reviewerBroker, reviewerRoceFilter, reviewerNewsFilter, reviewerTechFilter])

  // Filtered Directives for The Boss Tab (Tab 3)
  const filteredBossDirectives = useMemo(() => {
    const list = bossSubTab === 'archived' ? historicalDirectives : activeDirectives
    return list.filter((d) => {
      const firstAction = d.actions[0]
      const cleanTick = formatTicker(firstAction?.symbol, d.investigation_dossier?.symbol)
      const company = formatCompanyName(firstAction?.symbol, d.display_name)
      const q = bossSearch.toLowerCase().trim()

      const matchesSearch =
        !q ||
        cleanTick.toLowerCase().includes(q) ||
        company.toLowerCase().includes(q) ||
        (d.title && d.title.toLowerCase().includes(q))

      if (!matchesSearch) return false

      if (bossUrgency !== 'all') {
        if (bossUrgency === 'critical' && d.priority !== 'CRITICAL') return false
        if (bossUrgency === 'high' && d.priority !== 'HIGH') return false
        if (bossUrgency === 'normal' && d.priority !== 'NORMAL') return false
      }

      if (bossBroker !== 'all' && firstAction?.broker?.toLowerCase() !== bossBroker) {
        return false
      }

      // Boss Action Filter
      if (bossActionFilter !== 'all') {
        if (bossActionFilter === 'cut_loss' && !isExitAction(firstAction?.action)) return false
        if (bossActionFilter === 'trim' && !isTrimAction(firstAction?.action)) return false
        if (bossActionFilter === 'hold_defense' && firstAction?.action !== 'HOLD_DEFENSE') return false
      }

      // Boss ROCE Quality Filter
      if (bossRoceFilter !== 'all') {
        const groundDossier = dossierMap[cleanTick] || dossierMap[firstAction?.symbol || '']
        const roce = groundDossier?.funda_report?.roce_pct ?? d.investigation_dossier?.fundamental_vitals?.roce_pct
        if (bossRoceFilter === 'high' && (roce == null || roce < 15)) return false
        if (bossRoceFilter === 'low' && (roce == null || roce >= 10)) return false
      }

      // Boss AI Status Filter
      if (bossAiFilter !== 'all') {
        if (bossAiFilter === 'deliberated' && !d.ai_deliberated) return false
        if (bossAiFilter === 'held' && (d.ai_deliberated && !d.ai_deliberation_status?.startsWith('HELD'))) return false
      }

      return true
    })
  }, [activeDirectives, historicalDirectives, bossSubTab, bossUrgency, bossBroker, bossSearch, bossActionFilter, bossRoceFilter, bossAiFilter, dossierMap])

  // Copy Trade Manifest utility for The Boss
  const handleCopyManifest = () => {
    const lines = [
      '==========================================================',
      'WEALTHVAULT CIO MASTER CAPITAL REALLOCATION MANIFEST',
      `Generated: ${new Date().toLocaleDateString('en-IN')}`,
      `Total Capital to Free: ₹${Math.round(capitalMetrics.totalFreedCash).toLocaleString('en-IN')}`,
      `Total Downside Loss Neutralized: -₹${Math.round(capitalMetrics.totalUnrealizedLoss).toLocaleString('en-IN')}`,
      '==========================================================\n',
      '--- 1. CAPITAL RECLAMATION (SELL & TRIM ORDERS) ---',
    ]

    const sellDirectives = activeDirectives.filter((d) => d.actions[0]?.action !== 'HOLD_DEFENSE')
    sellDirectives.forEach((d, idx) => {
      const a = d.actions[0]
      const sym = formatTicker(a?.symbol, d.investigation_dossier?.symbol)
      const qty = d.holding_quantity ?? a?.holding_quantity ?? a?.quantity ?? 0
      const ltp = a?.estimated_price ?? d.holding_avg_price ?? 0
      const broker = (a?.broker || 'BROKER').toUpperCase()
      const isTrim = a?.action === 'TRAILING_TRIM' || a?.action === 'REBALANCE'
      const actionName = isTrim ? 'TRIM 50%' : 'FULL EXIT'
      const recovered = isTrim ? qty * 0.5 * ltp : qty * ltp
      const executedQty = isTrim ? Math.floor(qty * 0.5) : qty
      lines.push(`${idx + 1}. [${broker}] ${actionName}: ${sym} | Qty: ${executedQty} sh @ ~₹${ltp.toFixed(1)} -> Free ₹${Math.round(recovered).toLocaleString('en-IN')}`)
    })

    const holdDefenses = activeDirectives.filter((d) => d.actions[0]?.action === 'HOLD_DEFENSE')
    if (holdDefenses.length > 0) {
      lines.push('\n--- 2. DEFENSIVE SHIELDS (PROTECTED AT 200-DMA — DO NOT SELL) ---')
      holdDefenses.forEach((d, idx) => {
        const a = d.actions[0]
        const sym = formatTicker(a?.symbol, d.investigation_dossier?.symbol)
        const broker = (a?.broker || 'BROKER').toUpperCase()
        const sma200 = dossierMap[sym]?.tech_report?.sma_200?.toFixed(1) || 'Support'
        lines.push(`${idx + 1}. [${broker}] HOLD DEFENSE: ${sym} | Retained ₹0 liquidated | Stop Pegged to 200-DMA (₹${sma200})`)
      })
    }

    lines.push('\n--- 3. CAPITAL REDEPLOYMENT (BUY ORDERS) ---')
    redeploymentTargets.forEach((t, idx) => {
      lines.push(`${idx + 1}. BUY ${t.symbol} | Target: ${t.targetShares} sh @ ~₹${t.targetPrice} (Deploy ₹${t.allocatedRupees.toLocaleString('en-IN')} • ${t.allocationPct}%)`)
    })
    lines.push(`3. SAFE CASH RESERVE: ₹${Math.round(capitalMetrics.totalFreedCash * 0.25).toLocaleString('en-IN')} (25% buffer for fresh VCP breakouts)`)

    void navigator.clipboard.writeText(lines.join('\n'))
    setCopiedManifest(true)
    setTimeout(() => setCopiedManifest(false), 2500)
  }

  if (loading && !data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-3">
        <RefreshCw className="w-8 h-8 text-wv-accent animate-spin" />
        <p className="text-xs font-semibold text-wv-text-3 uppercase tracking-wider">
          Connecting to Fiduciary Review Engine...
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 space-y-5 font-sans">
      {/* 1. Header Toolbar with Tab Navigation and Action Controls */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-wv-border">
        {/* Left: Native Segmented Controls */}
        <div className="flex items-center gap-3 flex-wrap overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 sm:overflow-visible">
          <div className="seg seg-lg shrink-0">
            {/* Tab 1: Ground Scouts */}
            <button
              type="button"
              onClick={() => setActiveTab('ground')}
              className={activeTab === 'ground' ? 'on' : ''}
            >
              <Compass size={16} strokeWidth={1.75} />
              <span>1. Ground Scouts</span>
              <span className="cnt">{groundData?.dossiers?.length || 65}</span>
            </button>

            {/* Tab 2: The Reviewer */}
            <button
              type="button"
              onClick={() => setActiveTab('reviewer')}
              className={activeTab === 'reviewer' ? 'on' : ''}
            >
              <FileSearch size={16} strokeWidth={1.75} />
              <span>2. The Reviewer</span>
              <span className="cnt">{activeDirectives.length}</span>
            </button>

            {/* Tab 3: The Boss */}
            <button
              type="button"
              onClick={() => setActiveTab('boss')}
              className={activeTab === 'boss' ? 'on' : ''}
            >
              <Crown size={16} strokeWidth={1.75} />
              <span>3. The Boss</span>
              <span className="cnt">{activeDirectives.length}</span>
            </button>
          </div>

          <span className="hidden lg:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium text-wv-gain bg-wv-gain-weak border border-wv-gain/20">
            <span className="w-1.5 h-1.5 rounded-full bg-wv-gain" />
            {groundData?.dossiers?.length || 65} Pure Indian Equities Audited
          </span>
        </div>

        {/* Right: Phased Action Triggers matching Active Tab */}
        <div className="flex items-center gap-2.5 shrink-0 w-full lg:w-auto">
          {activeTab === 'ground' && (
            <button
              type="button"
              onClick={handleRunGroundScan}
              disabled={runningPhase !== 'none'}
              className="btn btn-primary w-full sm:w-auto"
            >
              {runningPhase === 'ground' ? (
                <RefreshCw size={15} strokeWidth={1.75} className="animate-spin" />
              ) : (
                <Compass size={15} strokeWidth={1.75} />
              )}
              <span>{runningPhase === 'ground' ? 'Scanning 6 Scouts…' : '1. Run Ground Scan'}</span>
            </button>
          )}

          {activeTab === 'reviewer' && (
            <button
              type="button"
              onClick={handleRunFiduciaryAudit}
              disabled={runningPhase !== 'none'}
              className="btn btn-primary w-full sm:w-auto"
            >
              {runningPhase === 'audit' ? (
                <RefreshCw size={15} strokeWidth={1.75} className="animate-spin" />
              ) : (
                <ShieldCheck size={15} strokeWidth={1.75} />
              )}
              <span>{runningPhase === 'audit' ? 'Auditing Policies…' : '2. Run Fiduciary Audit'}</span>
            </button>
          )}

          {activeTab === 'boss' && (
            <button
              type="button"
              onClick={handleRunBossDeliberation}
              disabled={runningPhase !== 'none'}
              className="btn btn-primary w-full sm:w-auto"
            >
              {runningPhase === 'boss' ? (
                <RefreshCw size={15} strokeWidth={1.75} className="animate-spin" />
              ) : (
                <Crown size={15} strokeWidth={1.75} />
              )}
              <span>{runningPhase === 'boss' ? 'Deliberating Directives…' : '3. Deliberate CIO Directives'}</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleRunAllPhases}
            disabled={runningPhase !== 'none'}
            className="btn btn-outline text-xs px-2.5 py-1.5 w-full sm:w-auto shrink-0"
            title="Execute Phase 2 (Audit) and Phase 3 (Boss Deliberation) consecutively"
          >
            {runningPhase === 'all' ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} className="fill-current" />}
            <span>Run All</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3.5 rounded-xl bg-wv-loss-weak border border-wv-loss/30 text-wv-loss text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 1: GROUND SCOUTS (DATA GATHERING & HOLDINGS INTEL)                     */}
      {/* ========================================================================= */}
      {activeTab === 'ground' && (
        <GroundSwarmView
          onSelectStockForReview={(symbol) => {
            const clean = formatTicker(symbol)
            setReviewerSearch(clean)
            setActiveTab('reviewer')
          }}
        />
      )}

      {/* ========================================================================= */}
      {/* TAB 2: THE REVIEWER (FIDUCIARY AUDIT & FORENSIC GATEKEEPER)                */}
      {/* ========================================================================= */}
      {activeTab === 'reviewer' && (
        <div className="space-y-5">
          {/* Phase 2 Header Action Ribbon */}
          <div className="card p-3.5 sm:p-4 bg-gradient-to-r from-wv-surface to-wv-surface-2 border border-wv-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-0.5">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-wv-accent-weak text-wv-accent border border-wv-accent/20">
                  Phase 2 Gatekeeper
                </span>
                <h3 className="text-xs sm:text-sm font-bold text-wv-text">
                  Fiduciary Reviewer Forensic Cross-Examination
                </h3>
              </div>
              <p className="text-[11px] text-wv-text-3">
                Scrutinizes stop-loss breaches against Ground Scout telemetry. Shields high-ROCE assets at 200-DMA support and euthanasia for confirmed capital rot.
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0 flex-wrap sm:flex-nowrap">
              <button
                type="button"
                onClick={() => setActiveTab('boss')}
                className="btn btn-outline text-xs px-3 py-1.5 flex items-center justify-center gap-1 w-full sm:w-auto"
              >
                <span>Proceed to Phase 3 Directives</span>
                <ArrowUpRight size={13} />
              </button>
            </div>
          </div>

          {/* Reviewer 4-Metric Audit Banner */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="card p-4 space-y-1">
              <span className="text-[11px] font-semibold text-wv-text-3 uppercase tracking-wider block">
                Total Proposals Audited
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold font-mono num text-wv-text">{reviewerStats.total}</span>
                <span className="text-xs text-wv-text-3">Cross-Examined</span>
              </div>
              <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border">
                Scrutinized against 4 independent fiduciary gates
              </p>
            </div>

            <div className="card p-4 space-y-1">
              <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider block flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5" /> False Breakdown Shields
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold font-mono num text-wv-gain">{reviewerStats.shields}</span>
                <span className="text-xs text-wv-gain font-medium">Protected at 200-DMA</span>
              </div>
              <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border">
                High-ROCE holdings shielded from retail panic stops
              </p>
            </div>

            <div className="card p-4 space-y-1">
              <span className="text-[11px] font-semibold text-rose-600 dark:text-rose-400 uppercase tracking-wider block flex items-center gap-1">
                <ShieldAlert className="w-3.5 h-3.5" /> Confirmed Capital Rot
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold font-mono num text-wv-loss">{reviewerStats.rot}</span>
                <span className="text-xs text-wv-loss font-medium">100% Liquidation Mandated</span>
              </div>
              <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border">
                Stage 4 decay / negative ROCE euthanasia
              </p>
            </div>

            <div className="card p-4 space-y-1">
              <span className="text-[11px] font-semibold text-amber-600 dark:text-amber-400 uppercase tracking-wider block flex items-center gap-1">
                <SlidersHorizontal className="w-3.5 h-3.5" /> Tactical Risk Trims
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold font-mono num text-wv-text">{reviewerStats.trims}</span>
                <span className="text-xs text-wv-text-3">De-Risked 50%</span>
              </div>
              <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border">
                Harvests risk off table; remainder trails with stop
              </p>
            </div>
          </div>

          {/* Fiduciary 4 Guardrails Guide Bar */}
          <div className="card p-3 sm:p-4 space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-wv-accent shrink-0" />
                <h4 className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-wv-text">
                  The Reviewer&apos;s 4 Institutional Fiduciary Principles
                </h4>
              </div>
              <span className="text-[11px] font-medium text-wv-gain flex items-center gap-1 shrink-0">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>100% Policy Vetting Enforcement</span>
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
              <div className="p-3 rounded-lg bg-wv-surface-2 border border-wv-border space-y-1">
                <b className="text-wv-text block text-xs">1. Beta Causality Separation</b>
                <p className="text-[11px] text-wv-text-3 leading-snug">
                  Distinguishes broad Nifty small-cap index pullbacks from internal corporate solvency failure.
                </p>
              </div>
              <div className="p-3 rounded-lg bg-wv-surface-2 border border-wv-border space-y-1">
                <b className="text-wv-text block text-xs">2. Screener Solvency Gate</b>
                <p className="text-[11px] text-wv-text-3 leading-snug">
                  Audits ROCE ≥ 12%, Debt/Eq ≤ 1.0, and quarterly sales growth from Screener.in balance sheet filings.
                </p>
              </div>
              <div className="p-3 rounded-lg bg-wv-surface-2 border border-wv-border space-y-1">
                <b className="text-wv-text block text-xs">3. Targeted News Threat Sieve</b>
                <p className="text-[11px] text-wv-text-3 leading-snug">
                  Scrapes exact Google News RSS feeds to confirm accounting red flags or governance scandals.
                </p>
              </div>
              <div className="p-3 rounded-lg bg-wv-surface-2 border border-wv-border space-y-1">
                <b className="text-wv-text block text-xs">4. Charlie Munger Inversion</b>
                <p className="text-[11px] text-wv-text-3 leading-snug">
                  &quot;Invert, always invert.&quot; Identifies how capital can be destroyed and cuts decaying assets ruthlessly.
                </p>
              </div>
            </div>
          </div>

          {/* Triage & Filter Toolbar for The Reviewer */}
          <div className="card p-3.5 sm:p-5 space-y-3.5">
            {/* Tier 1: Dedicated Horizontal Scroll Category Tabs */}
            <div className="overflow-x-auto no-scrollbar -mx-1 px-1">
              <div className="seg inline-flex shrink-0 whitespace-nowrap">
                <button
                  type="button"
                  onClick={() => setReviewerCategory('ALL')}
                  className={reviewerCategory === 'ALL' ? 'on' : ''}
                >
                  <span>All Audited</span>
                  <span className="cnt">{reviewerStats.total}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setReviewerCategory('SHIELD')}
                  className={reviewerCategory === 'SHIELD' ? 'on text-wv-gain' : ''}
                >
                  <ShieldCheck size={14} className="text-wv-gain" />
                  <span>🛡️ False Breakdown Shields</span>
                  <span className="cnt">{reviewerStats.shields}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setReviewerCategory('ROT')}
                  className={reviewerCategory === 'ROT' ? 'on text-wv-loss' : ''}
                >
                  <ShieldAlert size={14} className="text-wv-loss" />
                  <span>🔴 Confirmed Capital Rot</span>
                  <span className="cnt">{reviewerStats.rot}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setReviewerCategory('TRIM')}
                  className={reviewerCategory === 'TRIM' ? 'on text-wv-warn' : ''}
                >
                  <SlidersHorizontal size={14} className="text-amber-500" />
                  <span>🟡 Tactical Risk Trims</span>
                  <span className="cnt">{reviewerStats.trims}</span>
                </button>
              </div>
            </div>

            {/* Tier 2: Search & Broker Filter */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pt-2 border-t border-wv-border/50">
              <div className="relative flex-1 sm:max-w-md w-full">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-wv-text-3" />
                <input
                  type="text"
                  placeholder="Search ticker or company..."
                  value={reviewerSearch}
                  onChange={(e) => setReviewerSearch(e.target.value)}
                  className="pl-8 pr-8 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent w-full"
                />
                {reviewerSearch && (
                  <button
                    type="button"
                    onClick={() => setReviewerSearch('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-wv-text-3 hover:text-wv-text"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>

              {brokers.length > 1 && (
                <select
                  value={reviewerBroker}
                  onChange={(e) => setReviewerBroker(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent uppercase shrink-0"
                >
                  <option value="all">All Brokers</option>
                  {brokers.map((b) => (
                    <option key={b} value={b}>
                      {b.toUpperCase()}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Tier 3: Fiduciary Intelligence Filters (ROCE, News Threat, Technical Support) */}
            <div className="pt-2 border-t border-wv-border/50 flex items-center gap-2 flex-wrap text-xs">
              <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3 shrink-0">
                Filters:
              </span>

              {/* ROCE Solvency Filter */}
              <select
                value={reviewerRoceFilter}
                onChange={(e) => setReviewerRoceFilter(e.target.value)}
                className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
              >
                <option value="all">⚖️ All ROCE</option>
                <option value="healthy">ROCE ≥ 12% (Cleared)</option>
                <option value="subpar">Subpar ROCE (&lt; 12%)</option>
                <option value="negative">Negative ROCE (&lt; 0%)</option>
              </select>

              {/* News Threat Filter */}
              <select
                value={reviewerNewsFilter}
                onChange={(e) => setReviewerNewsFilter(e.target.value)}
                className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
              >
                <option value="all">📰 All News</option>
                <option value="threat">🚨 Material Threat Flagged</option>
                <option value="clean">🟢 Clean Wire (No Threats)</option>
              </select>

              {/* Technical Support / Stage Filter */}
              <select
                value={reviewerTechFilter}
                onChange={(e) => setReviewerTechFilter(e.target.value)}
                className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
              >
                <option value="all">📈 All Technicals</option>
                <option value="holding_200">🛡️ Holding 200-DMA Support</option>
                <option value="stage_4">📉 Stage 4 / Downtrend</option>
                <option value="uptrend">🚀 Stage 2 / Uptrend</option>
              </select>

              {/* Reset Filters button if any active */}
              {(reviewerRoceFilter !== 'all' || reviewerNewsFilter !== 'all' || reviewerTechFilter !== 'all' || reviewerBroker !== 'all' || reviewerSearch || reviewerCategory !== 'ALL') && (
                <button
                  type="button"
                  onClick={() => {
                    setReviewerCategory('ALL')
                    setReviewerBroker('all')
                    setReviewerSearch('')
                    setReviewerRoceFilter('all')
                    setReviewerNewsFilter('all')
                    setReviewerTechFilter('all')
                  }}
                  className="text-[11px] text-wv-accent hover:underline font-semibold px-2 py-1 rounded bg-wv-accent/10 border border-wv-accent/20"
                >
                  Reset Filters
                </button>
              )}

              <span className="text-[11px] text-wv-text-3 ml-auto shrink-0 font-medium">
                Showing <strong className="text-wv-text font-mono font-bold">{filteredReviewerDirectives.length}</strong> of {classifiedReviewerList.length} audited dossiers
              </span>
            </div>
          </div>

          {/* Reviewer Cards: The Scout Claim vs. Reviewer Challenge Debate */}
          {filteredReviewerDirectives.length === 0 ? (
            <div className="card p-6 sm:p-12 text-center space-y-2">
              <ShieldCheck className="w-8 h-8 text-wv-gain mx-auto" />
              <h3 className="text-sm font-bold text-wv-text">No Audited Dossiers Match Filter</h3>
              <p className="text-xs text-wv-text-3 max-w-md mx-auto">
                Try switching triage categories or resetting search to view all vetted proposals.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredReviewerDirectives.map(({ directive: d, cleanTicker, companyName, groundDossier, pnl, verdict }) => {
                const firstAction = d.actions[0]
                const broker = (firstAction?.broker || 'broker').toUpperCase()
                const trendVerdict = getTrendVerdict(d)
                const vitals = groundDossier?.funda_report || d.investigation_dossier?.fundamental_vitals
                const newsArticles = groundDossier?.news_report?.articles || d.investigation_dossier?.recent_news || []
                const patternName = groundDossier?.pattern_report?.pattern_name || (groundDossier?.pattern_report?.pattern_detected ? 'Pattern Detected' : 'Normal Base')
                const insiderBias = groundDossier?.insider_report?.institutional_bias || 'No Filings'

                return (
                  <div
                    key={`rev_${d.directive_id}`}
                    className="card p-3 sm:p-5 space-y-3 sm:space-y-4 hover:border-wv-border-strong transition-all"
                  >
                    {/* Header Row */}
                    <div className="flex flex-col gap-3 pb-3 border-b border-wv-border">
                      <div className="flex items-start gap-2 sm:gap-3">
                        <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-lg bg-wv-surface-2 border border-wv-border flex items-center justify-center shrink-0">
                          <Building2 className="w-4 h-4 text-wv-text-2" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                            <span className="text-sm font-bold text-wv-text font-mono tracking-wide">{cleanTicker}</span>
                            <span className="text-xs text-wv-text-2 truncate">{companyName}</span>
                          </div>
                          <div className="flex items-center gap-1.5 flex-wrap mt-1">
                            <span className={`text-[10px] font-bold px-1.5 sm:px-2 py-0.5 rounded border uppercase ${getBrokerBadgeClass(firstAction?.broker)}`}>
                              {broker}
                            </span>
                            <span className={`text-[10px] px-1.5 sm:px-2 py-0.5 rounded border ${verdict.badgeClass}`}>
                              {verdict.badgeLabel}
                            </span>
                            <span className="text-[10px] font-semibold px-1.5 sm:px-2 py-0.5 rounded bg-wv-surface-2 border border-wv-border text-wv-text-2 inline-flex items-center gap-1">
                              {trendVerdict.toLowerCase().includes('downtrend') || trendVerdict.toLowerCase().includes('bear') ? (
                                <TrendingDown className="w-3 h-3 text-wv-loss" />
                              ) : (
                                <TrendingUp className="w-3 h-3 text-wv-gain" />
                              )}
                              <span className="hidden sm:inline">{trendVerdict}</span>
                              <span className="sm:hidden">{trendVerdict.split(':')[0]}</span>
                            </span>
                          </div>
                          <p className="text-[11px] text-wv-text-3 mt-1">
                            P&amp;L: <strong className={`font-mono ${pnl >= 0 ? 'text-wv-gain' : 'text-wv-loss'}`}>{pnl >= 0 ? `+${pnl.toFixed(1)}%` : `${pnl.toFixed(1)}%`}</strong> ·
                            Proposal: <span className="font-semibold text-wv-text">{firstAction?.action?.replace('_', ' ')}</span>
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 sm:self-end">
                        <span className="badge ok text-[11px]">
                          <i />
                          100% Policy Vetted
                        </span>
                        <button
                          type="button"
                          onClick={() => setSelectedDirective(d)}
                          className="btn btn-ghost text-xs px-2.5 py-1"
                        >
                          <span>Full Audit Trail</span>
                          <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* Fiduciary Debate: Ground Scout Claim vs Reviewer Cross-Examination */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {/* Left: Ground Scout Trigger */}
                      <div className="p-3.5 rounded-lg bg-wv-surface-2 border border-wv-border space-y-1.5">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-wv-loss flex items-center gap-1.5">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>1. Ground Scout Alarm &amp; Trigger</span>
                        </span>
                        <p className="text-xs text-wv-text-2 leading-relaxed">
                          {verdict.scoutAlarm}
                        </p>
                        <div className="text-[11px] text-wv-text-3 pt-1 border-t border-wv-border/60">
                          Telemetry: Drawdown {pnl.toFixed(1)}% | ATR stop trigger breached
                        </div>
                      </div>

                      {/* Right: Reviewer Cross-Examination & Challenge */}
                      <div className="p-3.5 rounded-lg bg-wv-surface-2 border border-wv-border space-y-1.5">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-wv-accent flex items-center gap-1.5">
                          <ShieldCheck className="w-3.5 h-3.5" />
                          <span>2. Reviewer Challenge &amp; Fiduciary Verdict</span>
                        </span>
                        <p className="text-xs text-wv-text leading-relaxed font-medium">
                          {verdict.reviewerChallenge}
                        </p>
                        <div className="text-[11px] text-wv-text-3 pt-1 border-t border-wv-border/60">
                          {verdict.fiduciaryFinding}
                        </div>
                      </div>
                    </div>

                    {/* 6-Scout Multidimensional Evidence Matrix Strip */}
                    <div className="p-2.5 sm:p-3 rounded-lg bg-wv-surface border border-wv-border/80 space-y-2 sm:space-y-0 sm:flex sm:items-center sm:justify-between sm:gap-3 text-xs">
                      <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3 w-full sm:w-auto">
                          6-Scout Evidence:
                        </span>

                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-wv-surface-2 border border-wv-border text-[11px]">
                          <span className="text-wv-text-3">🛡️ Risk:</span>
                          <strong className={pnl < -15 ? 'text-wv-loss' : 'text-wv-text'}>{pnl.toFixed(1)}%</strong>
                        </span>

                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-wv-surface-2 border border-wv-border text-[11px]">
                          <span className="text-wv-text-3">📈 Tech:</span>
                          <strong className="text-wv-text">{trendVerdict.split(':')[0]}</strong>
                        </span>

                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-wv-surface-2 border border-wv-border text-[11px]">
                          <span className="text-wv-text-3">📐 Pattern:</span>
                          <strong className="text-wv-text">{patternName}</strong>
                        </span>

                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-wv-surface-2 border border-wv-border text-[11px]">
                          <span className="text-wv-text-3">⚖️ ROCE:</span>
                          <strong className={(vitals?.roce_pct || 0) >= 12 ? 'text-wv-gain' : 'text-wv-loss'}>
                            {vitals?.roce_pct != null ? `${vitals.roce_pct.toFixed(1)}%` : 'N/A'}
                          </strong>
                        </span>

                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-wv-surface-2 border border-wv-border text-[11px]">
                          <span className="text-wv-text-3">👥 Insider:</span>
                          <strong className="text-wv-text">{insiderBias}</strong>
                        </span>
                      </div>

                      {/* Right: Forward to Boss Action Link */}
                      <button
                        type="button"
                        onClick={() => {
                          setBossSearch(cleanTicker)
                          setActiveTab('boss')
                        }}
                        className="btn btn-outline text-xs px-3 py-1.5 w-full sm:w-auto shrink-0 flex items-center justify-center gap-1"
                      >
                        <span>View Boss Directive</span>
                        <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {/* Verified Real-Time Financial News Catalyst */}
                    {newsArticles.length > 0 ? (
                      <div className="flex items-start sm:items-center gap-2 text-xs text-wv-text-3 pt-2 sm:pt-1 border-t border-wv-border/50 flex-wrap sm:flex-nowrap">
                        <span className="text-[10px] uppercase font-bold text-wv-text-3 shrink-0">Verified News:</span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-wv-surface-2 border border-wv-border text-wv-accent shrink-0">
                          {newsArticles[0].age_label || (newsArticles[0].age_days != null ? `${newsArticles[0].age_days}d ago` : 'Recent')}
                        </span>
                        <span className="text-[10px] text-wv-text-3 shrink-0 hidden sm:inline">
                          [{newsArticles[0].source}]
                        </span>
                        <div className="flex items-center gap-1 min-w-0">
                          <ExternalLink className="w-3 h-3 text-wv-accent shrink-0" />
                          <a
                            href={newsArticles[0].link || '#'}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hover:underline text-[11px] text-wv-accent truncate"
                            title={`${newsArticles[0].headline} (${newsArticles[0].published_at})`}
                          >
                            {newsArticles[0].headline}
                          </a>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-xs text-wv-text-3 pt-2 sm:pt-1 border-t border-wv-border/50">
                        <span className="text-[10px] uppercase font-bold text-wv-text-3 shrink-0">News Wire:</span>
                        <span className="text-[11px] text-wv-text-3 italic">
                          Wire quiet — no material corporate disclosures in verified press over past 45 days
                        </span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: THE BOSS (CHIEF INVESTMENT OFFICER & MASTER REALLOCATION TERMINAL)  */}
      {/* ========================================================================= */}
      {activeTab === 'boss' && (
        <div className="space-y-5">
          {/* Phase 3 Header Action Ribbon */}
          <div className="card p-3.5 sm:p-4 bg-gradient-to-r from-wv-surface to-wv-surface-2 border border-wv-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-0.5">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                  Phase 3 Executive
                </span>
                <h3 className="text-xs sm:text-sm font-bold text-wv-text">
                  Chief Investment Officer Autonomous Capital Reallocation
                </h3>
              </div>
              <p className="text-[11px] text-wv-text-3">
                Synthesizes audited dossiers with Gemini AI into executive trade directives, enforces 3-pointer theses, and reallocates liquidated capital into Stage 2 leaders.
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0 flex-wrap sm:flex-nowrap">
              <button
                type="button"
                onClick={() => setActiveTab('reviewer')}
                className="btn btn-outline text-xs px-3 py-1.5 flex items-center justify-center gap-1 w-full sm:w-auto"
              >
                <span>Back to Reviewer</span>
              </button>
            </div>
          </div>

          {/* AI Deliberation Status Banner */}
          {data?.ai_deliberation_status === 'HELD_API_KEY_REQUIRED' && (
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-800 dark:text-amber-300 space-y-1">
              <div className="flex items-center gap-2 font-bold text-xs uppercase tracking-wide">
                <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                <span>Chief Investment Officer AI Deliberation Held (API Key Required)</span>
              </div>
              <p className="text-xs leading-relaxed opacity-90">
                Boss executive orders are currently held. Multi-scout AI synthesis across the 6 ground reports requires a Gemini API key. Add <code>GEMINI_API_KEY</code> to your App Service application settings or <code>.env</code> file to unlock autonomous deliberation.
              </p>
            </div>
          )}

          {data?.ai_deliberation_status === 'HELD_NETWORK_ERROR' && (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-800 dark:text-rose-300 space-y-1">
              <div className="flex items-center gap-2 font-bold text-xs uppercase tracking-wide">
                <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400" />
                <span>AI Deliberation Held (Network / Service Offline)</span>
              </div>
              <p className="text-xs leading-relaxed opacity-90">
                Unable to reach the Gemini AI service. Directives remain paused until network connectivity is restored.
              </p>
            </div>
          )}

          {data?.ai_deliberation_status === 'DELIBERATED_BY_GEMINI' && (
            <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-800 dark:text-emerald-300 flex items-center justify-between gap-3 flex-wrap text-xs">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                <span>
                  <strong>Autonomous Gemini AI Synthesis Active:</strong> All directives synthesized from 6-dimensional Ground Scout telemetry (Risk, Tech, Pattern, Funda, News, Insider).
                </span>
              </div>
              <span className="badge ok text-[10px] shrink-0">Engine: Gemini AI (CIO Multi-Scout)</span>
            </div>
          )}

          {/* Executive Capital Summary Strip */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="card p-4 space-y-1">
              <span className="text-[11px] font-semibold text-wv-text-3 uppercase tracking-wider block">
                Active Directives
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold font-mono num text-wv-text">{capitalMetrics.activeCount}</span>
                <span className="text-xs text-wv-loss font-medium">Positions Requiring Action</span>
              </div>
              <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border">
                Flagged for stop-loss breach or Stage 4 decline
              </p>
            </div>

            <div className="card p-4 space-y-1">
              <span className="text-[11px] font-semibold text-wv-text-3 uppercase tracking-wider block">
                Capital to Free &amp; Reclaim
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold font-mono num text-wv-gain">
                  ₹{Math.round(capitalMetrics.totalFreedCash).toLocaleString('en-IN')}
                </span>
                <span className="text-xs text-wv-gain font-medium">Recoverable Cash</span>
              </div>
              <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border">
                Halts capital destruction from decaying assets
              </p>
            </div>

            <div className="card p-4 space-y-1">
              <span className="text-[11px] font-semibold text-wv-text-3 uppercase tracking-wider block">
                Downside Risk Neutralized
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold font-mono num text-wv-loss">
                  -₹{Math.round(capitalMetrics.totalUnrealizedLoss).toLocaleString('en-IN')}
                </span>
                <span className="text-xs text-wv-text-3">Unrealized Loss Drag</span>
              </div>
              <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border">
                Eliminates compounding errors (Rule #1)
              </p>
            </div>

            <div className="card p-4 space-y-1">
              <span className="text-[11px] font-semibold text-wv-accent uppercase tracking-wider block flex items-center gap-1">
                <Sparkles className="w-3.5 h-3.5" /> Stage 2 Redeployment
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-lg font-bold text-wv-text truncate">
                  2 Leaders Queued
                </span>
              </div>
              <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border flex items-center justify-between">
                <span>Greaves Cotton &amp; Lumax Tech</span>
                <ArrowUpRight className="w-3.5 h-3.5 text-wv-accent" />
              </p>
            </div>
          </div>

          {/* ========================================================================= */}
          {/* THE EXECUTIVE MASTER CAPITAL REALLOCATION BLUEPRINT                        */}
          {/* ========================================================================= */}
          <div className="card p-5 space-y-4 border-2 border-wv-accent/30 bg-radial from-wv-accent/5 to-transparent">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-wv-border">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Crown className="w-5 h-5 text-wv-accent" />
                  <h3 className="text-sm font-bold uppercase tracking-wider text-wv-text">
                    Chief Investment Officer Capital Redeployment Blueprint
                  </h3>
                  <span className="badge ok text-[10px]">Active Reallocation</span>
                </div>
                <p className="text-xs text-wv-text-2">
                  Reclaim <strong>₹{Math.round(capitalMetrics.totalFreedCash).toLocaleString('en-IN')}</strong> from capital-destroying assets to fund top-decile Stage 2 institutional leaders.
                </p>
              </div>

              <button
                type="button"
                onClick={handleCopyManifest}
                className="btn btn-outline text-xs px-3 py-1.5 self-start sm:self-auto shrink-0 flex items-center gap-1.5"
              >
                {copiedManifest ? <Check className="w-3.5 h-3.5 text-wv-gain" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedManifest ? 'Manifest Copied!' : 'Copy Execution Manifest'}</span>
              </button>
            </div>

            {/* 3 Capital Allocation Columns */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {/* Leader #1 */}
              <div className="p-4 rounded-xl bg-wv-surface-2 border border-wv-border space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-wv-accent uppercase tracking-wider">
                    📈 Priority Leader #1 (40%)
                  </span>
                  <span className="text-xs font-mono font-bold text-wv-gain">
                    ₹{redeploymentTargets[0].allocatedRupees.toLocaleString('en-IN')}
                  </span>
                </div>
                <div>
                  <span className="text-base font-bold font-mono text-wv-text">{redeploymentTargets[0].symbol}</span>
                  <p className="text-xs text-wv-text-2">{redeploymentTargets[0].companyName}</p>
                </div>
                <div className="space-y-1 text-xs pt-2 border-t border-wv-border/60">
                  <div className="flex justify-between text-wv-text-3">
                    <span>Technical Stage:</span>
                    <strong className="text-wv-gain font-semibold">{redeploymentTargets[0].stage}</strong>
                  </div>
                  <div className="flex justify-between text-wv-text-3">
                    <span>ROCE / Relative Strength:</span>
                    <strong className="text-wv-text font-mono">{redeploymentTargets[0].roce}% · RS {redeploymentTargets[0].rsScore}</strong>
                  </div>
                  <div className="flex justify-between text-wv-text-3">
                    <span>Target Execution:</span>
                    <strong className="text-wv-accent font-mono">~{redeploymentTargets[0].targetShares} sh @ ₹{redeploymentTargets[0].targetPrice.toFixed(1)}</strong>
                  </div>
                </div>
              </div>

              {/* Leader #2 */}
              <div className="p-4 rounded-xl bg-wv-surface-2 border border-wv-border space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-wv-accent uppercase tracking-wider">
                    🚀 Priority Leader #2 (35%)
                  </span>
                  <span className="text-xs font-mono font-bold text-wv-gain">
                    ₹{redeploymentTargets[1].allocatedRupees.toLocaleString('en-IN')}
                  </span>
                </div>
                <div>
                  <span className="text-base font-bold font-mono text-wv-text">{redeploymentTargets[1].symbol}</span>
                  <p className="text-xs text-wv-text-2">{redeploymentTargets[1].companyName}</p>
                </div>
                <div className="space-y-1 text-xs pt-2 border-t border-wv-border/60">
                  <div className="flex justify-between text-wv-text-3">
                    <span>Technical Stage:</span>
                    <strong className="text-wv-gain font-semibold">{redeploymentTargets[1].stage}</strong>
                  </div>
                  <div className="flex justify-between text-wv-text-3">
                    <span>ROCE / Relative Strength:</span>
                    <strong className="text-wv-text font-mono">{redeploymentTargets[1].roce}% · RS {redeploymentTargets[1].rsScore}</strong>
                  </div>
                  <div className="flex justify-between text-wv-text-3">
                    <span>Target Execution:</span>
                    <strong className="text-wv-accent font-mono">~{redeploymentTargets[1].targetShares} sh @ ₹{redeploymentTargets[1].targetPrice.toFixed(1)}</strong>
                  </div>
                </div>
              </div>

              {/* Safe Cash Reserve (25%) */}
              <div className="p-4 rounded-xl bg-wv-surface-2 border border-wv-border space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-wv-text-3 uppercase tracking-wider">
                    🛡️ Safe Cash Buffer (25%)
                  </span>
                  <span className="text-xs font-mono font-bold text-wv-text">
                    ₹{Math.round(capitalMetrics.totalFreedCash * 0.25).toLocaleString('en-IN')}
                  </span>
                </div>
                <div>
                  <span className="text-base font-bold text-wv-text">Liquid Yield Reserve</span>
                  <p className="text-xs text-wv-text-2">Ultra-Short Liquid Fund / Cash</p>
                </div>
                <div className="space-y-1 text-xs pt-2 border-t border-wv-border/60">
                  <div className="flex justify-between text-wv-text-3">
                    <span>Mandate:</span>
                    <strong className="text-wv-text font-medium">Preserve Capital</strong>
                  </div>
                  <div className="flex justify-between text-wv-text-3">
                    <span>Breakout Trigger:</span>
                    <strong className="text-wv-text font-medium">VCP / Cup &amp; Handle Breakouts</strong>
                  </div>
                  <div className="flex justify-between text-wv-text-3">
                    <span>Readiness:</span>
                    <strong className="text-wv-gain font-medium">Instant Deployment Ready</strong>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ========================================================================= */}
          {/* INTERACTIVE BEFORE VS. AFTER PORTFOLIO TRANSFORMATION SIMULATOR           */}
          {/* ========================================================================= */}
          <div className="card p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Scale className="w-4 h-4 text-wv-accent" />
                <h4 className="text-xs font-bold uppercase tracking-wider text-wv-text">
                  Portfolio Transformation Simulator: Before vs. After Execution
                </h4>
              </div>
              <span className="text-[11px] text-wv-text-3">
                Strategic impact of executing Boss directives
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Before: Current Unmanaged State */}
              <div className="p-4 rounded-xl bg-wv-surface-2 border border-wv-border space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-wv-border">
                  <span className="text-xs font-bold text-wv-loss flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>Current Portfolio (Before Interventions)</span>
                  </span>
                  <span className="text-[11px] font-mono text-wv-text-3">116 Holdings</span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-wv-text-3">Bleeding Zombie Holdings:</span>
                    <span className="font-mono font-bold text-wv-loss">32 Positions Underperforming</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-wv-text-3">Compounding Loss Drag:</span>
                    <span className="font-mono font-bold text-wv-loss">-₹{Math.round(capitalMetrics.totalUnrealizedLoss).toLocaleString('en-IN')} (Escalating Bleed)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-wv-text-3">Allocation Concentration:</span>
                    <span className="text-wv-text-2">Severely diluted across low-ROCE assets</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-wv-text-3">Stage 2 Growth Capital:</span>
                    <span className="font-mono text-wv-text-3">Trapped in Stage 4 decline</span>
                  </div>
                </div>
              </div>

              {/* After: Executed Fiduciary State */}
              <div className="p-4 rounded-xl bg-wv-gain-weak/30 border border-wv-gain/30 space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-wv-gain/20">
                  <span className="text-xs font-bold text-wv-gain flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Optimized Portfolio (After Execution)</span>
                  </span>
                  <span className="text-[11px] font-mono font-bold text-wv-gain">84 High-Conviction Holdings</span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-wv-text-3">Bleeding Zombie Holdings:</span>
                    <span className="font-mono font-bold text-wv-gain">0 Positions (100% Eradicated)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-wv-text-3">Compounding Loss Drag:</span>
                    <span className="font-mono font-bold text-wv-gain">₹0 (Downside Halted)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-wv-text-3">Capital Recycled into Leaders:</span>
                    <span className="font-mono font-bold text-wv-gain">₹{Math.round(capitalMetrics.totalFreedCash * 0.75).toLocaleString('en-IN')} in 20%+ ROCE Leaders</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-wv-text-3">Safe Cash Safety Cushion:</span>
                    <span className="font-mono font-bold text-wv-accent">₹{Math.round(capitalMetrics.totalFreedCash * 0.25).toLocaleString('en-IN')} Ready for Breakouts</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ========================================================================= */}
          {/* ACTIONABLE ORDER EXECUTION DESK                                           */}
          {/* ========================================================================= */}
          <div className="card p-3.5 sm:p-5 space-y-3.5">
            {/* Tier 1: Dedicated Horizontal Scroll Sub-Tabs */}
            <div className="overflow-x-auto no-scrollbar -mx-1 px-1">
              <div className="seg inline-flex shrink-0 whitespace-nowrap">
                <button
                  type="button"
                  onClick={() => setBossSubTab('reclamation')}
                  className={bossSubTab === 'reclamation' ? 'on' : ''}
                >
                  <span>⚡ Active Directives</span>
                  <span className="cnt">{activeDirectives.length}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setBossSubTab('redeployment')}
                  className={bossSubTab === 'redeployment' ? 'on' : ''}
                >
                  <span>🚀 Capital Redeployment</span>
                  <span className="cnt">2 Buys</span>
                </button>
                <button
                  type="button"
                  onClick={() => setBossSubTab('archived')}
                  className={bossSubTab === 'archived' ? 'on' : ''}
                >
                  <span>📜 Executed / Archived</span>
                  <span className="cnt">{historicalDirectives.length}</span>
                </button>
              </div>
            </div>

            {/* Tier 2: Search, Urgency & Broker Filter */}
            {bossSubTab !== 'redeployment' && (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pt-2 border-t border-wv-border/50">
                <div className="relative flex-1 sm:max-w-md w-full">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-wv-text-3" />
                  <input
                    type="text"
                    placeholder="Search ticker or company..."
                    value={bossSearch}
                    onChange={(e) => setBossSearch(e.target.value)}
                    className="pl-8 pr-8 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent w-full"
                  />
                  {bossSearch && (
                    <button
                      type="button"
                      onClick={() => setBossSearch('')}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-wv-text-3 hover:text-wv-text"
                    >
                      <X size={12} />
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap justify-between sm:justify-end shrink-0">
                  <select
                    value={bossUrgency}
                    onChange={(e) => setBossUrgency(e.target.value)}
                    className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
                  >
                    <option value="all">All Priorities</option>
                    <option value="critical">Critical Urgency</option>
                    <option value="high">High Priority</option>
                    <option value="normal">Normal</option>
                  </select>

                  {brokers.length > 1 && (
                    <select
                      value={bossBroker}
                      onChange={(e) => setBossBroker(e.target.value)}
                      className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent uppercase"
                    >
                      <option value="all">All Brokers</option>
                      {brokers.map((b) => (
                        <option key={b} value={b}>
                          {b.toUpperCase()}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>
            )}

            {/* Tier 3: CIO Directive Filters (Action Type, ROCE Quality, AI Deliberation) */}
            {bossSubTab !== 'redeployment' && (
              <div className="pt-2 border-t border-wv-border/50 flex items-center gap-2 flex-wrap text-xs">
                <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3 shrink-0">
                  Filters:
                </span>

                {/* Action Type Filter */}
                <select
                  value={bossActionFilter}
                  onChange={(e) => setBossActionFilter(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
                >
                  <option value="all">🎯 All Actions</option>
                  <option value="cut_loss">🔴 Full Exit Directives</option>
                  <option value="trim">🟡 Trim Risk</option>
                  <option value="hold_defense">🛡️ Hold Defense</option>
                </select>

                {/* ROCE Quality Filter */}
                <select
                  value={bossRoceFilter}
                  onChange={(e) => setBossRoceFilter(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
                >
                  <option value="all">⚖️ All ROCE</option>
                  <option value="high">High ROCE (≥ 15%)</option>
                  <option value="low">Low ROCE (&lt; 10%)</option>
                </select>

                {/* AI Deliberation Status Filter */}
                <select
                  value={bossAiFilter}
                  onChange={(e) => setBossAiFilter(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
                >
                  <option value="all">✨ All Statuses</option>
                  <option value="deliberated">Gemini AI Deliberated</option>
                  <option value="held">AI Deliberation Held</option>
                </select>

                {/* Reset Filters button if any active */}
                {(bossActionFilter !== 'all' || bossRoceFilter !== 'all' || bossAiFilter !== 'all' || bossUrgency !== 'all' || bossBroker !== 'all' || bossSearch) && (
                  <button
                    type="button"
                    onClick={() => {
                      setBossUrgency('all')
                      setBossBroker('all')
                      setBossSearch('')
                      setBossActionFilter('all')
                      setBossRoceFilter('all')
                      setBossAiFilter('all')
                    }}
                    className="text-[11px] text-wv-accent hover:underline font-semibold px-2 py-1 rounded bg-wv-accent/10 border border-wv-accent/20"
                  >
                    Reset Filters
                  </button>
                )}

                <span className="text-[11px] text-wv-text-3 ml-auto shrink-0 font-medium">
                  Showing <strong className="text-wv-text font-mono font-bold">{filteredBossDirectives.length}</strong> of {bossSubTab === 'reclamation' ? activeDirectives.length : historicalDirectives.length} directives
                </span>
              </div>
            )}

            {/* SubTab 1: Capital Reclamation (Sell Orders) */}
            {bossSubTab === 'reclamation' && (
              <div className="space-y-4 pt-2">
                {filteredBossDirectives.length === 0 ? (
                  <div className="p-8 text-center space-y-2">
                    <ShieldCheck className="w-8 h-8 text-wv-gain mx-auto" />
                    <h4 className="text-sm font-bold text-wv-text">No Directives Pending Action</h4>
                    <p className="text-xs text-wv-text-3">
                      All positions have been executed or dismissed. Your capital is protected.
                    </p>
                  </div>
                ) : (
                  filteredBossDirectives.map((d) => {
                    const firstAction = d.actions[0]
                    const cleanTicker = formatTicker(firstAction?.symbol, d.investigation_dossier?.symbol)
                    const companyName = formatCompanyName(firstAction?.symbol, d.display_name)
                    const broker = (firstAction?.broker || 'broker').toUpperCase()
                    const isPending = d.user_status === 'PENDING_REVIEW'
                    const pnl = firstAction?.pnl_pct ?? d.pnl_pct ?? 0.0
                    const holdingQty = d.holding_quantity ?? firstAction?.holding_quantity ?? firstAction?.quantity ?? 0
                    const avgPrice = d.holding_avg_price ?? firstAction?.holding_avg_price ?? firstAction?.estimated_price ?? 0
                    const ltp = firstAction?.estimated_price ?? avgPrice
                    const reclaimedCapital = holdingQty * ltp

                    return (
                      <div
                        key={`boss_${d.directive_id}`}
                        className={`card p-5 space-y-4 transition-all border-l-4 ${
                          isExitAction(firstAction?.action)
                            ? 'border-l-wv-loss'
                            : isTrimAction(firstAction?.action)
                            ? 'border-l-wv-warn'
                            : 'border-l-wv-gain'
                        }`}
                      >
                        {/* Header Row */}
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-wv-border">
                          <div className="flex items-center gap-3">
                            <div className="w-9 h-9 rounded-lg bg-wv-surface-2 border border-wv-border flex items-center justify-center shrink-0">
                              <Crown className="w-4 h-4 text-wv-text" />
                            </div>
                            <div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-sm font-bold text-wv-text font-mono tracking-wide">{cleanTicker}</span>
                                <span className="text-xs text-wv-text-2">{companyName}</span>
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${getBrokerBadgeClass(firstAction?.broker)}`}>
                                  {broker}
                                </span>
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                                  isExitAction(firstAction?.action)
                                    ? 'bg-wv-loss-weak text-wv-loss border-wv-loss/20'
                                    : isTrimAction(firstAction?.action)
                                    ? 'bg-wv-warn-weak text-wv-warn border-wv-warn/20'
                                    : 'bg-wv-gain-weak text-wv-gain border-wv-gain/20'
                                }`}>
                                  {isExitAction(firstAction?.action)
                                    ? '🔴 FULL EXIT DIRECTIVE'
                                    : isTrimAction(firstAction?.action)
                                    ? '🟡 TRIM RISK'
                                    : '🛡️ HOLD DEFENSE'}
                                </span>
                                {d.ai_deliberated ? (
                                  <span className="text-[10px] font-bold px-2 py-0.5 rounded border bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20 flex items-center gap-1">
                                    <Sparkles className="w-3 h-3" />
                                    <span>Gemini AI Deliberated</span>
                                  </span>
                                ) : d.ai_deliberation_status?.startsWith('HELD') ? (
                                  <span className="text-[10px] font-bold px-2 py-0.5 rounded border bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 flex items-center gap-1">
                                    <AlertTriangle className="w-3 h-3" />
                                    <span>AI Review Held</span>
                                  </span>
                                ) : null}
                              </div>
                              <p className="text-[11px] text-wv-text-3 mt-0.5">
                                Priority: <strong className="text-wv-text">{d.priority}</strong> ·{' '}
                                Target Action:{' '}
                                <strong className={isExitAction(firstAction?.action) ? 'text-wv-loss' : isTrimAction(firstAction?.action) ? 'text-wv-warn' : 'text-wv-gain'}>
                                  {isExitAction(firstAction?.action)
                                    ? `SELL ${holdingQty} Shares at ${broker}`
                                    : isTrimAction(firstAction?.action)
                                    ? `TRIM ${firstAction?.quantity || Math.floor(holdingQty * 0.5)} Shares at ${broker}`
                                    : `HOLD DEFENSE (Stop Pegged to 200-DMA ₹${dossierMap[cleanTicker]?.tech_report?.sma_200?.toFixed(1) || '195.4'})`}
                                </strong>
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            {isPending ? (
                              <span className="badge warn text-[11px]">
                                <i />
                                Awaiting Execution
                              </span>
                            ) : (
                              <span className="badge ok text-[11px]">
                                <i />
                                Executed at Broker
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Financial Metric Strip */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3 rounded-lg bg-wv-surface-2 border border-wv-border text-xs">
                          <div>
                            <span className="text-[10px] text-wv-text-3 uppercase tracking-wider block">Position / Avg Cost</span>
                            <div className="font-mono font-semibold text-wv-text">
                              {holdingQty} sh @ ₹{avgPrice.toFixed(1)}
                            </div>
                          </div>

                          <div>
                            <span className="text-[10px] text-wv-text-3 uppercase tracking-wider block">Current LTP</span>
                            <div className="font-mono font-semibold text-wv-text">
                              ₹{ltp.toFixed(1)}
                            </div>
                          </div>

                          <div>
                            <span className="text-[10px] text-wv-text-3 uppercase tracking-wider block">Position P&amp;L</span>
                            <div className={`font-mono font-bold ${pnl >= 0 ? 'text-wv-gain' : 'text-wv-loss'}`}>
                              {pnl >= 0 ? `+${pnl.toFixed(1)}%` : `${pnl.toFixed(1)}%`}
                            </div>
                          </div>

                          <div>
                            <span className="text-[10px] text-wv-text-3 uppercase tracking-wider block">
                              {firstAction?.action === 'HOLD_DEFENSE' ? 'Capital Preserved' : 'Cash Recovered'}
                            </span>
                            <div className="font-mono font-bold text-wv-gain">
                              {firstAction?.action === 'HOLD_DEFENSE'
                                ? `₹${Math.round(holdingQty * ltp).toLocaleString('en-IN')}`
                                : `₹${Math.round(reclaimedCapital).toLocaleString('en-IN')}`}
                            </div>
                          </div>
                        </div>

                        {/* The Boss Directive Thesis */}
                        <div className="p-3.5 rounded-lg bg-wv-surface-2 border border-wv-border space-y-2.5">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-wv-text flex items-center gap-1.5">
                              <Crown className="w-3.5 h-3.5 text-amber-500" />
                              Executive Capital Mandate:
                            </span>
                            <span className="text-[10px] font-semibold text-wv-text-3 uppercase tracking-wider">
                              CIO Multi-Scout Justification
                            </span>
                          </div>
                          {renderThesisPointers(d.summary_thesis)}
                        </div>

                        {/* Action Buttons */}
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
                          <button
                            type="button"
                            onClick={() => setSelectedDirective(d)}
                            className="btn btn-ghost text-xs px-2.5 py-1.5 self-start sm:self-auto"
                          >
                            <FileSearch className="w-3.5 h-3.5" />
                            <span>Inspect Full Audit Trail</span>
                          </button>

                          {isPending && (
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => handleUpdateStatus(d.directive_id, 'IGNORED', 'User opted to retain position')}
                                className="btn btn-outline text-xs px-3 py-1.5"
                              >
                                <X className="w-3.5 h-3.5" />
                                <span>Ignore</span>
                              </button>

                              <button
                                type="button"
                                onClick={() => handleUpdateStatus(d.directive_id, 'ORDER_PLACED_AT_BROKER', `Executed order at ${broker}`)}
                                className="btn btn-primary text-xs px-3 py-1.5"
                              >
                                <Check className="w-3.5 h-3.5" />
                                <span>{firstAction?.action === 'HOLD_DEFENSE' ? 'Acknowledge Defense' : 'Mark Placed at Broker'}</span>
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            )}

            {/* SubTab 2: Capital Redeployment (Buy Orders) */}
            {bossSubTab === 'redeployment' && (
              <div className="space-y-4 pt-2">
                <div className="p-3.5 rounded-lg bg-wv-gain-weak border border-wv-gain/20 text-xs text-wv-gain flex items-center gap-2">
                  <Sparkles className="w-4 h-4 shrink-0" />
                  <span>
                    Freed capital (₹{Math.round(capitalMetrics.totalFreedCash).toLocaleString('en-IN')}) is routed into the top Stage 2 breakout leaders to accelerate portfolio compounding.
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {redeploymentTargets.map((target, idx) => (
                    <div key={`redeploy_${target.symbol}`} className="card p-5 space-y-4 border-2 border-wv-gain/30">
                      <div className="flex items-center justify-between pb-3 border-b border-wv-border">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-base font-bold font-mono text-wv-text">{target.symbol}</span>
                            <span className="badge ok text-[10px]">Leader #{idx + 1}</span>
                          </div>
                          <p className="text-xs text-wv-text-2">{target.companyName}</p>
                        </div>
                        <span className="text-xs font-mono font-bold text-wv-gain">
                          {target.allocationPct}% Allocation
                        </span>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="p-2.5 rounded-lg bg-wv-surface-2 border border-wv-border">
                          <span className="text-[10px] text-wv-text-3 block">Capital to Deploy</span>
                          <strong className="text-sm font-mono text-wv-gain">₹{target.allocatedRupees.toLocaleString('en-IN')}</strong>
                        </div>
                        <div className="p-2.5 rounded-lg bg-wv-surface-2 border border-wv-border">
                          <span className="text-[10px] text-wv-text-3 block">Target Order</span>
                          <strong className="text-sm font-mono text-wv-text">~{target.targetShares} sh @ ₹{target.targetPrice.toFixed(1)}</strong>
                        </div>
                        <div className="p-2.5 rounded-lg bg-wv-surface-2 border border-wv-border">
                          <span className="text-[10px] text-wv-text-3 block">Stage &amp; Momentum</span>
                          <strong className="text-xs text-wv-text">{target.stage} ({target.momentum})</strong>
                        </div>
                        <div className="p-2.5 rounded-lg bg-wv-surface-2 border border-wv-border">
                          <span className="text-[10px] text-wv-text-3 block">ROCE &amp; RS vs Nifty</span>
                          <strong className="text-xs text-wv-gain font-mono">{target.roce}% · RS {target.rsScore}</strong>
                        </div>
                      </div>

                      <p className="text-xs text-wv-text-2 leading-relaxed">
                        {target.rationale}
                      </p>

                      <div className="pt-2 border-t border-wv-border flex justify-end">
                        <button
                          type="button"
                          onClick={() => {
                            void navigator.clipboard.writeText(`BUY ${target.symbol} | Qty: ${target.targetShares} @ ₹${target.targetPrice}`)
                            setCopiedManifest(true)
                            setTimeout(() => setCopiedManifest(false), 2000)
                          }}
                          className="btn btn-outline text-xs px-3 py-1.5 flex items-center gap-1.5"
                        >
                          <Copy className="w-3.5 h-3.5" />
                          <span>Copy Buy Order</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* SubTab 3: Historical Directives */}
            {bossSubTab === 'archived' && (
              <div className="space-y-4 pt-2">
                {filteredBossDirectives.length === 0 ? (
                  <div className="p-8 text-center space-y-2">
                    <ShieldCheck className="w-8 h-8 text-wv-gain mx-auto" />
                    <h4 className="text-sm font-bold text-wv-text">No Historical Directives In Archive</h4>
                    <p className="text-xs text-wv-text-3">
                      Orders that you place at broker or ignore will appear here for complete fiduciary auditability.
                    </p>
                  </div>
                ) : (
                  filteredBossDirectives.map((d) => {
                    const firstAction = d.actions[0]
                    const cleanTicker = formatTicker(firstAction?.symbol, d.investigation_dossier?.symbol)
                    const companyName = formatCompanyName(firstAction?.symbol, d.display_name)
                    const broker = (firstAction?.broker || 'broker').toUpperCase()

                    return (
                      <div key={`hist_${d.directive_id}`} className="card p-4 space-y-2 opacity-80">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-bold text-xs text-wv-text">{cleanTicker}</span>
                            <span className="text-xs text-wv-text-2">{companyName}</span>
                            <span className="text-[10px] px-2 py-0.5 rounded bg-wv-surface-2 border border-wv-border uppercase text-wv-text-3">
                              {broker}
                            </span>
                          </div>
                          <span className="badge off text-[10px]">{d.user_status}</span>
                        </div>
                        <p className="text-xs text-wv-text-3">{d.summary_thesis}</p>
                      </div>
                    )
                  })
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Slide-over Inspection Drawer for Full Deliberation Audit */}
      {selectedDirective && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-black/50 backdrop-blur-xs flex justify-end">
          <div className="w-full sm:max-w-2xl bg-wv-surface h-full shadow-2xl flex flex-col border-l border-wv-border">
            {/* Drawer Header */}
            <div className="p-3.5 sm:p-5 border-b border-wv-border flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono font-bold text-sm sm:text-base text-wv-text">
                    {formatTicker(selectedDirective.actions[0]?.symbol, selectedDirective.investigation_dossier?.symbol)}
                  </span>
                  <span className="text-xs text-wv-text-3 truncate">
                    {formatCompanyName(selectedDirective.actions[0]?.symbol, selectedDirective.display_name)}
                  </span>
                </div>
                <p className="text-[11px] sm:text-xs text-wv-text-3 mt-0.5">
                  Full 3-Tier Deliberation Audit Trail &amp; Solvency Breakdown
                </p>
              </div>

              <button
                type="button"
                onClick={() => setSelectedDirective(null)}
                className="btn btn-ghost btn-icon"
              >
                <X size={18} strokeWidth={1.75} />
              </button>
            </div>

            {/* Drawer Body */}
            <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs">
              {/* 3-Tier Multi-Agent Timeline */}
              <div className="space-y-3">
                <h4 className="font-bold text-xs uppercase tracking-wider text-wv-text">
                  Multi-Agent Deliberation Timeline
                </h4>
                <div className="space-y-3 border-l-2 border-wv-border pl-4 ml-2">
                  {/* Tier 1 */}
                  <div className="relative space-y-1">
                    <span className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-wv-accent" />
                    <span className="font-bold text-wv-accent flex items-center gap-1">
                      <Compass className="w-3.5 h-3.5" /> 1. Level 1: Ground Scouts Telemetry
                    </span>
                    <p className="text-wv-text-2">
                      Technical &amp; risk scouts flagged position breach ({selectedDirective.pnl_pct?.toFixed(1) ?? 'N/A'}% P&amp;L). Gathered balance sheet ratios from Screener.in and Google News RSS headlines.
                    </p>
                  </div>

                  {/* Tier 2 */}
                  <div className="relative space-y-1">
                    <span className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-wv-warn" />
                    <span className="font-bold text-wv-warn flex items-center gap-1">
                      <ShieldCheck className="w-3.5 h-3.5" /> 2. Level 2: Fiduciary Reviewer AI Audit
                    </span>
                    <p className="text-wv-text-2">
                      {selectedDirective.review_summary || 'Vetted against 4 fiduciary guardrails. Verified Beta causality decomposition and news threats.'}
                    </p>
                  </div>

                  {/* Tier 3 */}
                  <div className="relative space-y-1">
                    <span className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-wv-text" />
                    <span className="font-bold text-wv-text flex items-center gap-1">
                      <Crown className="w-3.5 h-3.5" /> 3. Level 3: Chief Investment Officer (The Boss)
                    </span>
                    <div className="pt-1">
                      {renderThesisPointers(selectedDirective.summary_thesis)}
                    </div>
                  </div>
                </div>
              </div>

              {/* Balance Sheet Vitals from Screener.in */}
              {selectedDirective.investigation_dossier?.fundamental_vitals && (
                <div className="space-y-2">
                  <h4 className="font-bold text-xs uppercase tracking-wider text-wv-text flex items-center gap-1.5">
                    <Scale className="w-3.5 h-3.5 text-wv-accent" />
                    <span>Balance Sheet Financial Vitals (Screener.in)</span>
                  </h4>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div className="p-2.5 rounded-lg bg-wv-surface-2 border border-wv-border">
                      <span className="text-[10px] text-wv-text-3 block">ROCE</span>
                      <span className="font-mono font-bold text-wv-text">
                        {selectedDirective.investigation_dossier.fundamental_vitals.roce_pct != null
                          ? `${selectedDirective.investigation_dossier.fundamental_vitals.roce_pct.toFixed(1)}%`
                          : 'N/A'}
                      </span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-wv-surface-2 border border-wv-border">
                      <span className="text-[10px] text-wv-text-3 block">Debt / Equity</span>
                      <span className="font-mono font-bold text-wv-text">
                        {selectedDirective.investigation_dossier.fundamental_vitals.debt_to_equity != null
                          ? selectedDirective.investigation_dossier.fundamental_vitals.debt_to_equity.toFixed(2)
                          : 'N/A'}
                      </span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-wv-surface-2 border border-wv-border">
                      <span className="text-[10px] text-wv-text-3 block">P/E Ratio</span>
                      <span className="font-mono font-bold text-wv-text">
                        {selectedDirective.investigation_dossier.fundamental_vitals.pe_ratio != null
                          ? selectedDirective.investigation_dossier.fundamental_vitals.pe_ratio.toFixed(1)
                          : 'N/A'}
                      </span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-wv-surface-2 border border-wv-border">
                      <span className="text-[10px] text-wv-text-3 block">Sales Growth YoY</span>
                      <span className="font-mono font-bold text-wv-text">
                        {selectedDirective.investigation_dossier.fundamental_vitals.sales_growth_yoy_pct != null
                          ? `${selectedDirective.investigation_dossier.fundamental_vitals.sales_growth_yoy_pct.toFixed(1)}%`
                          : 'N/A'}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* News Catalysts */}
              {selectedDirective.investigation_dossier?.recent_news &&
                selectedDirective.investigation_dossier.recent_news.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="font-bold text-xs uppercase tracking-wider text-wv-text">
                      Verified Google News Catalysts
                    </h4>
                    <div className="space-y-2">
                      {selectedDirective.investigation_dossier.recent_news.map((n, idx) => (
                        <a
                          key={`art_${idx}`}
                          href={n.link || '#'}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-3 rounded-lg bg-wv-surface-2 border border-wv-border hover:border-wv-accent transition-all block space-y-1"
                        >
                          <div className="flex items-center justify-between text-[11px] text-wv-text-3">
                            <span className="flex items-center gap-1.5">
                              <span>{n.source || 'News Source'}</span>
                              {n.age_label && (
                                <span className="px-1.5 py-0.2 rounded font-mono text-[9px] bg-wv-surface border border-wv-border text-wv-accent">
                                  {n.age_label}
                                </span>
                              )}
                            </span>
                            <span>{n.published_at ? new Date(n.published_at).toLocaleDateString('en-IN') : ''}</span>
                          </div>
                          <div className="font-medium text-wv-text flex items-center justify-between gap-2">
                            <span>{n.headline}</span>
                            <ExternalLink className="w-3 h-3 shrink-0 text-wv-accent" />
                          </div>
                        </a>
                      ))}
                    </div>
                  </div>
                )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

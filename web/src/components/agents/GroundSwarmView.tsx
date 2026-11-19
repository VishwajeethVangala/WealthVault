import React, { useEffect, useState, useCallback, useMemo } from 'react'
import {
  ShieldAlert,
  FileSearch,
  ChevronRight,
  RefreshCw,
  Layers,
  Search,
  Scale,
  ExternalLink,
  Activity,
  Newspaper,
  Briefcase,
  X,
  AlertTriangle,
  Zap,
  Table,
  LayoutGrid,
} from 'lucide-react'
import { fetchGroundSwarmOverview, fetchGroundStatus } from '../../utils/api'
import type { GroundStockDossier, GroundSwarmOverview } from '../../types'
import { formatTicker, formatCompanyName } from '../../utils/tickerFormat'

interface GroundSwarmViewProps {
  onSelectStockForReview?: (symbol: string) => void
}

export const isActionRequired = (d: GroundStockDossier): { required: boolean; reason: string } => {
  if (d.risk_report?.stop_loss_breach) {
    return { required: true, reason: `Hard Stop Loss Breach (${(d.risk_report.pnl_pct ?? 0).toFixed(1)}%)` }
  }
  if (d.risk_report?.deep_drawdown_breach) {
    return { required: true, reason: `Deep Drawdown Warning (${(d.risk_report.pnl_pct ?? 0).toFixed(1)}%)` }
  }
  if (d.tech_report?.stage_verdict?.toLowerCase().includes('stage 4')) {
    return { required: true, reason: 'Stage 4 Capitulation / Severe Downtrend' }
  }
  if (d.news_report?.material_threat) {
    return { required: true, reason: 'Material Forensic News Threat (Probe / Fraud / Regulatory)' }
  }
  return { required: false, reason: '' }
}

export const isHighConvictionBreakout = (d: GroundStockDossier): { isBreakout: boolean; tag: string } => {
  const p = d.pattern_report
  if (!p || !p.pattern_detected || p.bias !== 'BULLISH') return { isBreakout: false, tag: '' }
  if (p.is_low_volume_trap) return { isBreakout: false, tag: '' }
  const techScore = d.tech_report?.momentum_score ?? 0
  const isStage2 = d.tech_report?.stage_verdict?.toLowerCase().includes('stage 2')
  if (techScore >= 3 || isStage2) {
    const volStr = p.volume_surge_ratio ? `${p.volume_surge_ratio.toFixed(1)}x Vol` : 'Breakout'
    return { isBreakout: true, tag: `${p.pattern_name || 'Pattern'} (${volStr})` }
  }
  return { isBreakout: false, tag: '' }
}

export const GroundSwarmView: React.FC<GroundSwarmViewProps> = ({ onSelectStockForReview }) => {
  const [data, setData] = useState<GroundSwarmOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [barrierFilter, setBarrierFilter] = useState<'all' | 'ready' | 'in_progress'>('all')
  const [inspectedDossier, setInspectedDossier] = useState<GroundStockDossier | null>(null)
  const [triageFilter, setTriageFilter] = useState<'all' | 'danger' | 'opportunity' | 'baseline'>('all')
  const [viewMode, setViewMode] = useState<'table' | 'cards'>('table')
  const [patternFilter, setPatternFilter] = useState<string>('all')
  const [roceFilter, setRoceFilter] = useState<string>('all')
  const [newsFilter, setNewsFilter] = useState<string>('all')
  const [stageFilter, setStageFilter] = useState<string>('all')

  const loadData = useCallback(async () => {
    try {
      const res = await fetchGroundSwarmOverview()
      setData(res)
      setScanning(res.status?.is_scanning || false)
      setError(null)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch ground scout dossiers'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  // Polling when a scan is active
  useEffect(() => {
    if (!scanning) return
    const interval = setInterval(async () => {
      try {
        const status = await fetchGroundStatus()
        setScanning(status.is_scanning)
        if (!status.is_scanning) {
          void loadData()
        } else {
          setData((prev) => (prev ? { ...prev, status } : prev))
        }
      } catch {
        // silent fail during poll
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [scanning, loadData])

  // Filter dossiers
  const filteredDossiers = useMemo(() => {
    if (!data?.dossiers) return []
    return data.dossiers.filter((d) => {
      const q = searchQuery.toLowerCase().trim()
      const cleanTick = formatTicker(d.symbol)
      const compName = formatCompanyName(d.symbol, d.company_name)

      const matchesSearch =
        !q ||
        cleanTick.toLowerCase().includes(q) ||
        compName.toLowerCase().includes(q) ||
        d.symbol.toLowerCase().includes(q)

      if (!matchesSearch) return false

      if (barrierFilter === 'ready' && d.barrier_status !== 'READY_FOR_REVIEW') return false
      if (barrierFilter === 'in_progress' && d.barrier_status !== 'IN_PROGRESS') return false

      // Pattern Filter
      if (patternFilter !== 'all') {
        const pat = d.pattern_report
        if (patternFilter === 'has_pattern' && !pat?.pattern_detected) return false
        if (patternFilter === 'vcp' && !pat?.pattern_name?.toLowerCase().includes('vcp')) return false
        if (patternFilter === 'cup_handle' && !pat?.pattern_name?.toLowerCase().includes('cup')) return false
        if (patternFilter === 'double_bottom' && !pat?.pattern_name?.toLowerCase().includes('bottom')) return false
        if (patternFilter === 'volume_surge' && (pat?.volume_surge_ratio || 0) < 1.4) return false
        if (patternFilter === 'trap' && !pat?.is_low_volume_trap) return false
      }

      // ROCE Solvency Filter
      if (roceFilter !== 'all') {
        const roce = d.funda_report?.roce_pct
        if (roceFilter === 'elite' && (roce == null || roce < 20)) return false
        if (roceFilter === 'healthy' && (roce == null || roce < 12)) return false
        if (roceFilter === 'subpar' && (roce == null || roce >= 12 || roce < 0)) return false
        if (roceFilter === 'negative' && (roce == null || roce >= 0)) return false
      }

      // News Sentiment Filter
      if (newsFilter !== 'all') {
        const news = d.news_report
        if (newsFilter === 'threat' && !news?.material_threat) return false
        if (newsFilter === 'has_news' && (news?.articles_scanned || 0) <= 0) return false
        if (newsFilter === 'positive' && !news?.articles?.some((a) => a.sentiment === 'POSITIVE')) return false
        if (newsFilter === 'negative' && !news?.articles?.some((a) => a.sentiment === 'NEGATIVE')) return false
      }

      // Technical Stage Filter
      if (stageFilter !== 'all') {
        const tech = d.tech_report
        if (stageFilter === 'stage_2' && !tech?.stage_verdict?.toLowerCase().includes('stage 2')) return false
        if (stageFilter === 'stage_4' && !tech?.stage_verdict?.toLowerCase().includes('stage 4')) return false
        if (stageFilter === 'above_200' && (!tech?.sma_200 || (tech.current_price ?? 0) < tech.sma_200)) return false
        if (stageFilter === 'below_200' && (!tech?.sma_200 || (tech.current_price ?? 0) >= tech.sma_200)) return false
      }

      return true
    })
  }, [data?.dossiers, searchQuery, barrierFilter, patternFilter, roceFilter, newsFilter, stageFilter])

  // 3-Bucket Triage Classification
  const buckets = useMemo(() => {
    const danger: GroundStockDossier[] = []
    const opportunity: GroundStockDossier[] = []
    const baseline: GroundStockDossier[] = []

    for (const d of filteredDossiers) {
      if (isActionRequired(d).required) {
        danger.push(d)
      } else if (isHighConvictionBreakout(d).isBreakout) {
        opportunity.push(d)
      } else {
        baseline.push(d)
      }
    }

    return { danger, opportunity, baseline }
  }, [filteredDossiers])

  const displayedList = useMemo(() => {
    if (triageFilter === 'danger') return buckets.danger
    if (triageFilter === 'opportunity') return buckets.opportunity
    if (triageFilter === 'baseline') return buckets.baseline
    return filteredDossiers
  }, [triageFilter, buckets, filteredDossiers])

  // Stats
  const stats = useMemo(() => {
    const list = data?.dossiers || []
    return {
      total: list.length,
      ready: list.filter((d) => d.barrier_status === 'READY_FOR_REVIEW').length,
      inProgress: list.filter((d) => d.barrier_status === 'IN_PROGRESS').length,
      patternsFound: list.filter((d) => d.pattern_report?.pattern_detected).length,
    }
  }, [data?.dossiers])

  return (
    <div className="space-y-5">
      {/* 1. Ground Scouts KPI Rail */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card p-4 space-y-1">
          <span className="text-[11px] font-semibold text-wv-text-3 uppercase tracking-wider block">
            Audited Holdings
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono num text-wv-text">{stats.total}</span>
            <span className="text-xs text-wv-text-3">Stocks Scanned</span>
          </div>
          <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border">
            100% Pure Indian Equities (NSE/BSE)
          </p>
        </div>

        <div className="card p-4 space-y-1">
          <span className="text-[11px] font-semibold text-wv-text-3 uppercase tracking-wider block">
            Barrier Passed (Ready)
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono num text-wv-gain">{stats.ready}</span>
            <span className="text-xs text-wv-gain font-medium">/ {stats.total} Ready</span>
          </div>
          <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border">
            6/6 Scouts Completed Data Gathering
          </p>
        </div>

        <div className="card p-4 space-y-1">
          <span className="text-[11px] font-semibold text-wv-text-3 uppercase tracking-wider block">
            Active / Pending
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono num text-wv-text-2">{stats.inProgress}</span>
            <span className="text-xs text-wv-text-3">In Flight</span>
          </div>
          <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border">
            Autonomous rate-limited crawling
          </p>
        </div>

        <div className="card p-4 space-y-1">
          <span className="text-[11px] font-semibold text-wv-accent uppercase tracking-wider block">
            Patterns Detected
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono num text-wv-accent">{stats.patternsFound}</span>
            <span className="text-xs text-wv-accent font-medium">Formations</span>
          </div>
          <p className="text-[11px] text-wv-text-3 pt-2 border-t border-wv-border">
            VCP, Cup &amp; Handle, Double Bottoms
          </p>
        </div>
      </div>

      {/* Live Scan Status Banner */}
      {scanning && (
        <div className="p-3 bg-wv-accent-weak border border-wv-accent/30 rounded-xl flex items-center justify-between text-xs text-wv-accent animate-pulse">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 animate-spin" />
            <span>
              <strong>Ground Swarm Active:</strong> Crawling stock{' '}
              <span className="font-mono font-bold">{data?.status?.current_stock || '...'}</span> | Scout:{' '}
              <span className="font-semibold">{data?.status?.current_scout || 'Risk Scout'}</span>
            </span>
          </div>
          <span>Autonomous rate-limited crawl</span>
        </div>
      )}

      {error && (
        <div className="p-3 bg-wv-loss-weak border border-wv-loss/30 rounded-xl flex items-center gap-2 text-xs text-wv-loss">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 2. Unified Triage & Filter Toolbar */}
      <div className="card p-3.5 sm:p-4 space-y-3.5">
        {/* Tier 1: Dedicated Horizontal Scroll Triage Categories */}
        <div className="overflow-x-auto no-scrollbar -mx-1 px-1">
          <div className="seg inline-flex shrink-0 whitespace-nowrap">
            <button
              type="button"
              onClick={() => setTriageFilter('all')}
              className={triageFilter === 'all' ? 'on' : ''}
            >
              <span>All Holdings</span>
              <span className="cnt">{filteredDossiers.length}</span>
            </button>
            <button
              type="button"
              onClick={() => setTriageFilter('danger')}
              className={triageFilter === 'danger' ? 'on text-wv-loss' : ''}
            >
              <ShieldAlert size={14} className="text-wv-loss" />
              <span>1. Immediate Action</span>
              <span className="cnt">{buckets.danger.length}</span>
            </button>
            <button
              type="button"
              onClick={() => setTriageFilter('opportunity')}
              className={triageFilter === 'opportunity' ? 'on text-wv-gain' : ''}
            >
              <Zap size={14} className="text-wv-gain" />
              <span>2. Breakouts</span>
              <span className="cnt">{buckets.opportunity.length}</span>
            </button>
            <button
              type="button"
              onClick={() => setTriageFilter('baseline')}
              className={triageFilter === 'baseline' ? 'on' : ''}
            >
              <span>3. Quiet Baseline</span>
              <span className="cnt">{buckets.baseline.length}</span>
            </button>
          </div>
        </div>

        {/* Tier 2: Search, View Mode, and Quick Barrier Toggle */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pt-2 border-t border-wv-border/50">
          <div className="relative flex-1 sm:max-w-md w-full">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-wv-text-3" />
            <input
              type="text"
              placeholder="Search stock ticker or company..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-8 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent w-full"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-wv-text-3 hover:text-wv-text"
              >
                <X size={12} />
              </button>
            )}
          </div>

          <div className="flex items-center gap-2 justify-between sm:justify-end shrink-0">
            {/* Barrier Quick Toggle */}
            <select
              value={barrierFilter}
              onChange={(e) => setBarrierFilter(e.target.value as any)}
              className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
            >
              <option value="all">🛡️ All Barriers</option>
              <option value="ready">Ready (6/6 Scouts)</option>
              <option value="in_progress">In Flight</option>
            </select>

            {/* View Mode Toggle */}
            <div className="seg shrink-0">
              <button
                type="button"
                onClick={() => setViewMode('table')}
                className={viewMode === 'table' ? 'on' : ''}
                title="Institutional Table View"
              >
                <Table size={14} strokeWidth={1.75} />
                <span className="hidden sm:inline">Table</span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode('cards')}
                className={viewMode === 'cards' ? 'on' : ''}
                title="Card View"
              >
                <LayoutGrid size={14} strokeWidth={1.75} />
                <span className="hidden sm:inline">Cards</span>
              </button>
            </div>
          </div>
        </div>

        {/* Tier 3: Multi-dimensional Filter Bar (Patterns, ROCE, News, Stage, Reset) */}
        <div className="pt-2 border-t border-wv-border/50 flex items-center gap-2 flex-wrap text-xs">
          <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3 shrink-0">
            Filters:
          </span>

          {/* Pattern Filter */}
          <select
            value={patternFilter}
            onChange={(e) => setPatternFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
          >
            <option value="all">📐 All Patterns</option>
            <option value="has_pattern">Any Pattern Detected</option>
            <option value="vcp">VCP (Volatility Contraction)</option>
            <option value="cup_handle">Cup &amp; Handle</option>
            <option value="double_bottom">Double Bottom / Base</option>
            <option value="volume_surge">Volume Surge (≥ 1.4x)</option>
            <option value="trap">Low Volume Trap</option>
          </select>

          {/* ROCE Solvency Filter */}
          <select
            value={roceFilter}
            onChange={(e) => setRoceFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
          >
            <option value="all">⚖️ All ROCE</option>
            <option value="elite">Elite ROCE (≥ 20%)</option>
            <option value="healthy">Healthy ROCE (≥ 12%)</option>
            <option value="subpar">Subpar ROCE (&lt; 12%)</option>
            <option value="negative">Negative ROCE (&lt; 0%)</option>
          </select>

          {/* News Sentiment Filter */}
          <select
            value={newsFilter}
            onChange={(e) => setNewsFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
          >
            <option value="all">📰 All News</option>
            <option value="threat">🚨 Material Threat Flagged</option>
            <option value="positive">🟢 Positive Sentiment</option>
            <option value="negative">🔴 Negative Sentiment</option>
            <option value="has_news">Has News Articles</option>
          </select>

          {/* Technical Stage Filter */}
          <select
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-lg bg-wv-surface border border-wv-border text-xs text-wv-text focus:outline-none focus:border-wv-accent"
          >
            <option value="all">📈 All Stages</option>
            <option value="stage_2">Stage 2: Markup</option>
            <option value="stage_4">Stage 4: Capitulation / Downtrend</option>
            <option value="above_200">Above 200-DMA Support</option>
            <option value="below_200">Below 200-DMA Breakdown</option>
          </select>

          {/* Reset Filters button if any active */}
          {(patternFilter !== 'all' || roceFilter !== 'all' || newsFilter !== 'all' || stageFilter !== 'all' || barrierFilter !== 'all' || searchQuery) && (
            <button
              type="button"
              onClick={() => {
                setPatternFilter('all')
                setRoceFilter('all')
                setNewsFilter('all')
                setStageFilter('all')
                setBarrierFilter('all')
                setSearchQuery('')
              }}
              className="text-[11px] text-wv-accent hover:underline font-semibold px-2 py-1 rounded bg-wv-accent/10 border border-wv-accent/20"
            >
              Reset Filters
            </button>
          )}

          <span className="text-[11px] text-wv-text-3 ml-auto shrink-0 font-medium">
            Showing <strong className="text-wv-text font-mono font-bold">{displayedList.length}</strong> of {data?.dossiers?.length || 65} holdings
          </span>
        </div>
      </div>

      {/* 3. Stock Data Display */}
      {loading ? (
        <div className="card p-12 text-center text-wv-text-3 space-y-2">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto text-wv-accent" />
          <p className="text-xs">Loading Ground Swarm dossiers...</p>
        </div>
      ) : displayedList.length === 0 ? (
        <div className="card p-12 text-center text-wv-text-3 space-y-2">
          <FileSearch className="w-8 h-8 mx-auto text-wv-text-3" />
          <h3 className="font-semibold text-wv-text text-sm">No Ground Dossiers Match Filter</h3>
          <p className="text-xs max-w-md mx-auto">
            Try adjusting your search query or switching triage categories.
          </p>
        </div>
      ) : viewMode === 'table' ? (
        /* TABLE VIEW (Default, Institutional High-Density) */
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse min-w-[760px]">
              <thead>
                <tr className="border-b border-wv-border bg-wv-surface-2 text-wv-text-3 uppercase text-[10px] tracking-wider font-semibold">
                  <th className="py-3 px-4">Asset / Company</th>
                  <th className="py-3 px-3">Risk &amp; P&amp;L</th>
                  <th className="py-3 px-3">Stage / Technical</th>
                  <th className="py-3 px-3">Pattern Setup</th>
                  <th className="py-3 px-3">Fundamentals</th>
                  <th className="py-3 px-3">News Intel</th>
                  <th className="py-3 px-3">Status</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-wv-border">
                {displayedList.map((dos) => {
                  const cleanTick = formatTicker(dos.symbol)
                  const compName = formatCompanyName(dos.symbol, dos.company_name)
                  const pnl = dos.risk_report?.pnl_pct ?? 0.0
                  const dangerInfo = isActionRequired(dos)
                  const oppInfo = isHighConvictionBreakout(dos)
                  const isReady = dos.barrier_status === 'READY_FOR_REVIEW'
                  const funda = dos.funda_report
                  const tech = dos.tech_report
                  const pat = dos.pattern_report
                  const news = dos.news_report

                  return (
                    <tr
                      key={dos.symbol}
                      onClick={() => setInspectedDossier(dos)}
                      className="hover:bg-wv-surface-2/60 transition-colors cursor-pointer group"
                    >
                      {/* Asset & Company */}
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <div>
                            <div className="font-mono font-bold text-sm text-wv-text tracking-wide group-hover:text-wv-accent transition-colors">
                              {cleanTick}
                            </div>
                            <div className="text-[11px] text-wv-text-3 truncate max-w-[180px]">
                              {compName}
                            </div>
                          </div>
                          {dangerInfo.required && (
                            <span className="w-2 h-2 rounded-full bg-wv-loss shrink-0" title={dangerInfo.reason} />
                          )}
                          {!dangerInfo.required && oppInfo.isBreakout && (
                            <span className="w-2 h-2 rounded-full bg-wv-gain shrink-0" title={oppInfo.tag} />
                          )}
                        </div>
                      </td>

                      {/* Risk & P&L */}
                      <td className="py-3 px-3">
                        <div className={`font-mono font-bold ${pnl >= 0 ? 'text-wv-gain' : 'text-wv-loss'}`}>
                          {pnl >= 0 ? `+${pnl.toFixed(1)}%` : `${pnl.toFixed(1)}%`}
                        </div>
                        <div className="text-[10px] text-wv-text-3">
                          {dos.risk_report ? `${dos.risk_report.portfolio_weight_pct.toFixed(1)}% wt` : '-'}
                          {dos.risk_report?.stop_loss_breach && (
                            <span className="ml-1 text-wv-loss font-semibold">· Stop</span>
                          )}
                        </div>
                      </td>

                      {/* Stage & Momentum */}
                      <td className="py-3 px-3">
                        <div className="font-medium text-wv-text">
                          {tech?.stage_verdict?.split(':')[0] || 'Neutral'}
                        </div>
                        <div className="text-[10px] text-wv-text-3">
                          Score: <span className="font-mono font-semibold">{tech?.momentum_score ?? '-'}/5</span>
                          {tech?.rs_score_vs_nifty != null && (
                            <span className="ml-1">· RS {tech.rs_score_vs_nifty > 0 ? '+' : ''}{tech.rs_score_vs_nifty.toFixed(1)}%</span>
                          )}
                        </div>
                      </td>

                      {/* Pattern */}
                      <td className="py-3 px-3">
                        {pat?.pattern_detected ? (
                          <div>
                            <div className="font-medium text-wv-text truncate max-w-[140px]">
                              {pat.pattern_name}
                            </div>
                            <div className="text-[10px] text-wv-accent font-semibold">
                              {pat.volume_surge_ratio && pat.volume_surge_ratio >= 1.5
                                ? `⚡ ${pat.volume_surge_ratio.toFixed(1)}x Vol`
                                : pat.is_low_volume_trap
                                ? '⚠️ Low Vol'
                                : 'Forming'}
                            </div>
                          </div>
                        ) : (
                          <span className="text-wv-text-3 text-[11px]">—</span>
                        )}
                      </td>

                      {/* Fundamentals */}
                      <td className="py-3 px-3">
                        {funda?.status === 'COMPLETED' ? (
                          <div>
                            <div className="text-wv-text font-mono">
                              ROCE: <span className={funda.roce_pct != null && funda.roce_pct >= 12 ? 'text-wv-gain font-semibold' : 'text-wv-loss font-semibold'}>
                                {funda.roce_pct != null ? `${funda.roce_pct.toFixed(1)}%` : 'N/A'}
                              </span>
                            </div>
                            <div className="text-[10px] text-wv-text-3 font-mono">
                              D/E: {funda.debt_to_equity != null ? funda.debt_to_equity.toFixed(2) : '-'} · P/E: {funda.pe_ratio != null ? funda.pe_ratio.toFixed(1) : '-'}
                            </div>
                          </div>
                        ) : (
                          <span className="text-wv-text-3 text-[11px]">Pending</span>
                        )}
                      </td>

                      {/* News Intel */}
                      <td className="py-3 px-3">
                        {news?.status === 'COMPLETED' ? (
                          <div>
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                              news.material_threat || news.dominant_sentiment === 'NEGATIVE'
                                ? 'bg-wv-loss-weak text-wv-loss'
                                : news.dominant_sentiment === 'POSITIVE'
                                ? 'bg-wv-gain-weak text-wv-gain'
                                : 'bg-wv-surface-2 text-wv-text-3'
                            }`}>
                              {news.dominant_sentiment}
                            </span>
                            <div className="text-[10px] text-wv-text-3 mt-0.5">
                              {news.articles_scanned} scanned
                            </div>
                          </div>
                        ) : (
                          <span className="text-wv-text-3 text-[11px]">—</span>
                        )}
                      </td>

                      {/* Barrier Status */}
                      <td className="py-3 px-3">
                        {isReady ? (
                          <span className="badge ok text-[10px]">
                            <i />
                            Ready (6/6)
                          </span>
                        ) : (
                          <span className="badge warn text-[10px]">
                            <i />
                            Scouting
                          </span>
                        )}
                      </td>

                      {/* Action */}
                      <td className="py-3 px-4 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setInspectedDossier(dos)
                          }}
                          className="btn btn-ghost text-xs px-2 py-1"
                        >
                          <span>Telemetry</span>
                          <ChevronRight size={13} />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* CARDS VIEW (Clean, Restrained Grid) */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {displayedList.map((dos) => {
            const cleanTick = formatTicker(dos.symbol)
            const compName = formatCompanyName(dos.symbol, dos.company_name)
            const pnl = dos.risk_report?.pnl_pct ?? 0.0
            const dangerInfo = isActionRequired(dos)
            const oppInfo = isHighConvictionBreakout(dos)
            const isReady = dos.barrier_status === 'READY_FOR_REVIEW'

            return (
              <div
                key={dos.symbol}
                onClick={() => setInspectedDossier(dos)}
                className={`card p-4 space-y-3 cursor-pointer hover:border-wv-border-strong transition-all border-l-4 ${
                  dangerInfo.required
                    ? 'border-l-wv-loss'
                    : oppInfo.isBreakout
                    ? 'border-l-wv-gain'
                    : 'border-l-wv-border'
                }`}
              >
                {/* Header */}
                <div className="flex items-center justify-between pb-2 border-b border-wv-border">
                  <div>
                    <div className="font-mono font-bold text-sm text-wv-text">{cleanTick}</div>
                    <div className="text-xs text-wv-text-3 truncate max-w-[180px]">{compName}</div>
                  </div>
                  <div className={`font-mono font-bold text-sm ${pnl >= 0 ? 'text-wv-gain' : 'text-wv-loss'}`}>
                    {pnl >= 0 ? `+${pnl.toFixed(1)}%` : `${pnl.toFixed(1)}%`}
                  </div>
                </div>

                {/* Vitals Summary Strip */}
                <div className="grid grid-cols-3 gap-2 text-[11px] py-1 bg-wv-surface-2 rounded-lg p-2 font-mono">
                  <div>
                    <span className="text-wv-text-3 block text-[9px]">STAGE</span>
                    <span className="text-wv-text font-semibold truncate block">
                      {dos.tech_report?.stage_verdict?.split(':')[0] || 'Neutral'}
                    </span>
                  </div>
                  <div>
                    <span className="text-wv-text-3 block text-[9px]">ROCE</span>
                    <span className="text-wv-text font-semibold truncate block">
                      {dos.funda_report?.roce_pct != null ? `${dos.funda_report.roce_pct.toFixed(1)}%` : 'N/A'}
                    </span>
                  </div>
                  <div>
                    <span className="text-wv-text-3 block text-[9px]">NEWS</span>
                    <span className="text-wv-text font-semibold truncate block">
                      {dos.news_report?.dominant_sentiment || 'NEUTRAL'}
                    </span>
                  </div>
                </div>

                {/* Footer Status */}
                <div className="flex items-center justify-between text-xs pt-1">
                  {isReady ? (
                    <span className="badge ok text-[10px]">
                      <i />
                      Ready for Review
                    </span>
                  ) : (
                    <span className="badge warn text-[10px]">
                      <i />
                      Scouting in Progress
                    </span>
                  )}
                  <span className="text-wv-accent text-xs font-medium flex items-center gap-0.5">
                    <span>Inspect</span>
                    <ChevronRight size={13} />
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Slide-over Inspection Drawer for Ground Scout Radar Telemetry */}
      {inspectedDossier && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-black/50 backdrop-blur-xs flex justify-end">
          <div className="w-full sm:max-w-2xl bg-wv-surface h-full shadow-2xl flex flex-col border-l border-wv-border">
            {/* Drawer Header */}
            <div className="p-3.5 sm:p-5 border-b border-wv-border flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono font-bold text-sm sm:text-base text-wv-text">
                    {formatTicker(inspectedDossier.symbol)}
                  </span>
                  <span className="text-xs text-wv-text-3 truncate">
                    {formatCompanyName(inspectedDossier.symbol, inspectedDossier.company_name)}
                  </span>
                </div>
                <p className="text-[11px] sm:text-xs text-wv-text-3 mt-0.5">
                  6-Scout Radar Telemetry &amp; Foundational Evidence
                </p>
              </div>

              <div className="flex items-center gap-2">
                {onSelectStockForReview && (
                  <button
                    type="button"
                    onClick={() => {
                      onSelectStockForReview(inspectedDossier.symbol)
                      setInspectedDossier(null)
                    }}
                    className="btn btn-primary text-xs px-2.5 py-1 flex items-center gap-1"
                  >
                    <span>View Reviewer Audit</span>
                    <ChevronRight size={13} />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setInspectedDossier(null)}
                  className="btn btn-ghost btn-icon"
                >
                  <X size={18} strokeWidth={1.75} />
                </button>
              </div>
            </div>

            {/* Drawer Body: 6 Scout Detailed Breakdown */}
            <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs">
              {/* 1. Risk Scout */}
              <div className="p-4 rounded-xl bg-wv-surface-2 border border-wv-border space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs uppercase tracking-wider text-wv-text flex items-center gap-1.5">
                    <ShieldAlert className="w-3.5 h-3.5 text-wv-loss" />
                    <span>1. Risk Scout Telemetry</span>
                  </span>
                  <span className={`font-mono font-bold text-sm ${
                    (inspectedDossier.risk_report?.pnl_pct ?? 0) >= 0 ? 'text-wv-gain' : 'text-wv-loss'
                  }`}>
                    {(inspectedDossier.risk_report?.pnl_pct ?? 0).toFixed(1)}% P&amp;L
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-wv-text-2">
                  <div>Weight: <strong>{inspectedDossier.risk_report?.portfolio_weight_pct.toFixed(1)}%</strong></div>
                  <div>Stop Loss Breach: <strong>{inspectedDossier.risk_report?.stop_loss_breach ? 'YES' : 'NO'}</strong></div>
                  <div>Deep Drawdown: <strong>{inspectedDossier.risk_report?.deep_drawdown_breach ? 'YES' : 'NO'}</strong></div>
                  <div>Concentration: <strong>{inspectedDossier.risk_report?.over_concentration ? 'HIGH' : 'NORMAL'}</strong></div>
                </div>
              </div>

              {/* 2. Technical Scout */}
              <div className="p-4 rounded-xl bg-wv-surface-2 border border-wv-border space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs uppercase tracking-wider text-wv-text flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-wv-accent" />
                    <span>2. Technical &amp; Trend Scout</span>
                  </span>
                  <span className="font-mono font-bold text-sm text-wv-text">
                    Score: {inspectedDossier.tech_report?.momentum_score ?? 0}/5
                  </span>
                </div>
                <div className="space-y-1 text-wv-text-2">
                  <div>Stage Verdict: <strong>{inspectedDossier.tech_report?.stage_verdict}</strong></div>
                  <div>RS vs Nifty 50: <strong>{inspectedDossier.tech_report?.rs_score_vs_nifty?.toFixed(1) ?? 'N/A'}%</strong></div>
                  <div>200-SMA: <strong>₹{inspectedDossier.tech_report?.sma_200?.toFixed(1) ?? 'N/A'}</strong></div>
                  <div>Market Regime: <strong>{inspectedDossier.tech_report?.market_regime ?? 'NORMAL'}</strong></div>
                </div>
              </div>

              {/* 3. Pattern Scout */}
              <div className="p-4 rounded-xl bg-wv-surface-2 border border-wv-border space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs uppercase tracking-wider text-wv-text flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-wv-text-2" />
                    <span>3. Classical Pattern Scout</span>
                  </span>
                  <span className="badge info text-[10px]">
                    {inspectedDossier.pattern_report?.pattern_detected ? inspectedDossier.pattern_report.pattern_name : 'No Formation'}
                  </span>
                </div>
                {inspectedDossier.pattern_report?.pattern_detected && (
                  <div className="grid grid-cols-2 gap-2 text-wv-text-2">
                    <div>Pivot Price: <strong>₹{inspectedDossier.pattern_report.pivot_breakout_price?.toFixed(1) ?? '-'}</strong></div>
                    <div>Volume Surge: <strong>{inspectedDossier.pattern_report.volume_surge_ratio?.toFixed(1) ?? '1.0'}x</strong></div>
                    <div>Pattern Stage: <strong>{inspectedDossier.pattern_report.pattern_stage ?? 'Confirmed'}</strong></div>
                    <div>Low Vol Trap: <strong>{inspectedDossier.pattern_report.is_low_volume_trap ? 'YES' : 'NO'}</strong></div>
                  </div>
                )}
              </div>

              {/* 4. Fundamental Scout */}
              <div className="p-4 rounded-xl bg-wv-surface-2 border border-wv-border space-y-2">
                <span className="font-bold text-xs uppercase tracking-wider text-wv-text flex items-center gap-1.5">
                  <Scale className="w-3.5 h-3.5 text-wv-text-2" />
                  <span>4. Fundamental Solvency Scout (Screener.in)</span>
                </span>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center pt-1">
                  <div className="p-2 rounded bg-wv-surface border border-wv-border">
                    <span className="text-[10px] text-wv-text-3 block">ROCE</span>
                    <strong className="font-mono text-wv-text">
                      {inspectedDossier.funda_report?.roce_pct != null ? `${inspectedDossier.funda_report.roce_pct.toFixed(1)}%` : 'N/A'}
                    </strong>
                  </div>
                  <div className="p-2 rounded bg-wv-surface border border-wv-border">
                    <span className="text-[10px] text-wv-text-3 block">Debt/Eq</span>
                    <strong className="font-mono text-wv-text">
                      {inspectedDossier.funda_report?.debt_to_equity != null ? inspectedDossier.funda_report.debt_to_equity.toFixed(2) : 'N/A'}
                    </strong>
                  </div>
                  <div className="p-2 rounded bg-wv-surface border border-wv-border">
                    <span className="text-[10px] text-wv-text-3 block">P/E</span>
                    <strong className="font-mono text-wv-text">
                      {inspectedDossier.funda_report?.pe_ratio != null ? inspectedDossier.funda_report.pe_ratio.toFixed(1) : 'N/A'}
                    </strong>
                  </div>
                  <div className="p-2 rounded bg-wv-surface border border-wv-border">
                    <span className="text-[10px] text-wv-text-3 block">Pledged</span>
                    <strong className="font-mono text-wv-text">
                      {inspectedDossier.funda_report?.promoter_pledged_pct != null ? `${inspectedDossier.funda_report.promoter_pledged_pct.toFixed(1)}%` : '0%'}
                    </strong>
                  </div>
                </div>
              </div>

              {/* 5. News Scout */}
              <div className="p-4 rounded-xl bg-wv-surface-2 border border-wv-border space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs uppercase tracking-wider text-wv-text flex items-center gap-1.5">
                    <Newspaper className="w-3.5 h-3.5 text-wv-text-2" />
                    <span>5. News Sentiment Scout (Google News RSS)</span>
                  </span>
                  <span className="badge off text-[10px]">
                    {inspectedDossier.news_report?.articles_scanned ?? 0} Articles Scanned
                  </span>
                </div>
                {inspectedDossier.news_report?.articles && inspectedDossier.news_report.articles.length > 0 ? (
                  <div className="space-y-1.5 pt-1">
                    {inspectedDossier.news_report.articles.slice(0, 3).map((art, idx) => (
                      <a
                        key={`art_${idx}`}
                        href={art.link || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-2 rounded bg-wv-surface border border-wv-border hover:border-wv-accent transition-all block space-y-0.5"
                      >
                        <div className="text-[10px] text-wv-text-3 flex items-center justify-between">
                          <span>{art.source}</span>
                          <span>{art.published_at ? new Date(art.published_at).toLocaleDateString('en-IN') : ''}</span>
                        </div>
                        <div className="text-xs text-wv-text font-medium flex items-center justify-between gap-1">
                          <span className="truncate">{art.headline}</span>
                          <ExternalLink className="w-3 h-3 shrink-0 text-wv-accent" />
                        </div>
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-wv-text-3">No material forensic news headlines flagged.</p>
                )}
              </div>

              {/* 6. Insider Deals Scout */}
              <div className="p-4 rounded-xl bg-wv-surface-2 border border-wv-border space-y-2">
                <span className="font-bold text-xs uppercase tracking-wider text-wv-text flex items-center gap-1.5">
                  <Briefcase className="w-3.5 h-3.5 text-wv-text-2" />
                  <span>6. Insider Deals &amp; Bulk Filings (NSE/BSE)</span>
                </span>
                <div className="grid grid-cols-2 gap-2 text-wv-text-2">
                  <div>Institutional Bias: <strong>{inspectedDossier.insider_report?.institutional_bias ?? 'NO_DEALS'}</strong></div>
                  <div>Promoter Bias: <strong>{inspectedDossier.insider_report?.promoter_bias ?? 'NO_FILINGS'}</strong></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

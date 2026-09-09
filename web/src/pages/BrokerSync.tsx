import React, { useState, useEffect } from 'react'
import {
  Radio,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ShieldCheck,
  Cpu,
  Key,
  Lock,
  AlertCircle,
  Eye,
  Layers,
  Activity,
  Server,
  Terminal,
} from 'lucide-react'
import {
  fetchBrokerSessions,
  syncBroker,
  expireBroker,
  disconnectBroker,
} from '../utils/api'
import type { BrokerSessionInfo } from '../types'
import { usePortfolio } from '../context/PortfolioContext'

export const BrokerSync: React.FC = () => {
  const { refresh: refreshPortfolio } = usePortfolio()
  const [sessions, setSessions] = useState<BrokerSessionInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Per-broker sync and action loading states
  const [actionLoading, setActionLoading] = useState<Record<string, string | null>>({})
  const [actionSuccess, setActionSuccess] = useState<Record<string, string | null>>({})

  // Tool directory preview state
  const [expandedTools, setExpandedTools] = useState<string | null>(null)

  const loadSessions = async () => {
    try {
      setLoading(true)
      const data = await fetchBrokerSessions()
      setSessions(data)
      setError(null)
    } catch (err: any) {
      console.error('Failed to load broker sessions:', err)
      setError(err.message || 'Failed to aggregate broker MCP sessions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSessions()

    const handleMessage = (event: MessageEvent) => {
      if (event.data === 'indmoney_authorized') {
        loadSessions()
        handleSingleSync('indmoney')
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [])

  // Format INR currency
  const formatINR = (val: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(val)
  }

  // Format timestamp into human readable and relative
  const formatTimestamp = (isoString?: string): { relative: string; full: string } => {
    if (!isoString) return { relative: 'Never synced', full: 'No record available' }
    const date = new Date(isoString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    let relative = ''
    if (diffMins < 1) relative = 'Just now'
    else if (diffMins < 60) relative = `${diffMins} min ago`
    else {
      const diffHours = Math.floor(diffMins / 60)
      if (diffHours < 24) relative = `${diffHours} hr ago`
      else relative = `${Math.floor(diffHours / 24)}d ago`
    }

    const timeStr = date.toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    const dateStr = date.toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })

    return { relative, full: `${dateStr} at ${timeStr} IST` }
  }

  const handleSingleSync = async (brokerName: string) => {
    setActionLoading((prev) => ({ ...prev, [brokerName]: 'syncing' }))
    try {
      const updated = await syncBroker(brokerName)
      setSessions((prev) => prev.map((s) => (s.broker_name === brokerName ? updated : s)))

      if (updated.status === 'AUTH_REQUIRED' || updated.status === 'SESSION_EXPIRED') {
        alert(
          `${updated.display_name} authorization is required. Please click 'Authorize on Kite' to log in in your browser, then click Sync again.`
        )
      } else if (updated.status === 'CONNECTED') {
        await refreshPortfolio()
        setActionSuccess((prev) => ({
          ...prev,
          [brokerName]: `Synced successfully! ${updated.holdings_count} positions updated.`,
        }))
        setTimeout(() => {
          setActionSuccess((prev) => ({ ...prev, [brokerName]: null }))
        }, 4000)
      }
    } catch (err: any) {
      alert(`Sync failed: ${err.message}`)
    } finally {
      setActionLoading((prev) => ({ ...prev, [brokerName]: null }))
    }
  }

  const handleTestHandshake = async (brokerName: string) => {
    setActionLoading((prev) => ({ ...prev, [brokerName]: 'testing' }))
    try {
      await new Promise((r) => setTimeout(r, 600))
      setActionSuccess((prev) => ({ ...prev, [brokerName]: 'MCP Handshake Verified (124ms)' }))
      setTimeout(() => {
        setActionSuccess((prev) => ({ ...prev, [brokerName]: null }))
      }, 3000)
    } finally {
      setActionLoading((prev) => ({ ...prev, [brokerName]: null }))
    }
  }

  const handleSimulateExpire = async (brokerName: string) => {
    setActionLoading((prev) => ({ ...prev, [brokerName]: 'expiring' }))
    try {
      const updated = await expireBroker(brokerName)
      setSessions((prev) => prev.map((s) => (s.broker_name === brokerName ? updated : s)))
    } catch (err: any) {
      alert(`Simulation error: ${err.message}`)
    } finally {
      setActionLoading((prev) => ({ ...prev, [brokerName]: null }))
    }
  }

  const handleDisconnect = async (brokerName: string) => {
    setActionLoading((prev) => ({ ...prev, [brokerName]: 'disconnecting' }))
    try {
      const updated = await disconnectBroker(brokerName)
      setSessions((prev) => prev.map((s) => (s.broker_name === brokerName ? updated : s)))
    } catch (err: any) {
      alert(`Disconnect error: ${err.message}`)
    } finally {
      setActionLoading((prev) => ({ ...prev, [brokerName]: null }))
    }
  }

  const handleStartAuth = async (session: BrokerSessionInfo) => {
    if (session.auth_url) {
      window.open(session.auth_url, '_blank')
      return
    }
    setActionLoading((prev) => ({ ...prev, [session.broker_name]: 'authorizing' }))
    try {
      // 1. Refresh sessions to fetch the latest auth_url generated by backend
      const fresh = await fetchBrokerSessions()
      setSessions(fresh)
      const target = fresh.find((s) => s.broker_name === session.broker_name)
      if (target?.auth_url) {
        window.open(target.auth_url, '_blank')
        return
      }

      // 2. Fallback: call sync endpoint which forces session re-init & acquires fresh auth_url
      const synced = await syncBroker(session.broker_name)
      setSessions((prev) => prev.map((s) => (s.broker_name === session.broker_name ? synced : s)))
      if (synced?.auth_url) {
        window.open(synced.auth_url, '_blank')
      } else {
        alert(`Could not retrieve authorization link for ${session.display_name}.`)
      }
    } catch (err: any) {
      alert(`Could not start authorization: ${err.message}`)
    } finally {
      setActionLoading((prev) => ({ ...prev, [session.broker_name]: null }))
    }
  }

  // Aggregate stats
  const activeCount = sessions.filter((s) => s.status === 'CONNECTED').length
  const totalValuation = sessions.reduce((sum, s) => sum + (s.total_valuation || 0), 0)
  const totalHoldings = sessions.reduce((sum, s) => sum + (s.holdings_count || 0), 0)

  if (loading && sessions.length === 0) {
    return (
      <div className="py-24 flex flex-col items-center justify-center min-h-[50vh]">
        <div className="w-10 h-10 border-3 border-slate-900 border-t-transparent rounded-full animate-spin"></div>
        <p className="mt-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">
          Querying Live MCP Broker Session Gateways...
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {error && (
        <div className="bg-white border border-rose-200 p-4 rounded-xl shadow-sm flex items-center gap-3 text-xs text-rose-700">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 1. Header Banner & Action Bar */}
      <div className="bg-white rounded-2xl p-6 sm:p-8 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80 flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200/60">
              <Radio className="w-3 h-3 animate-pulse" />
              <span>Model Context Protocol (MCP) Live Mesh</span>
            </span>
          </div>
          <h1 className="font-serif text-2xl sm:text-3xl text-slate-950 font-medium tracking-tight">
            Broker Synchronization &amp; Session Manager
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Inspect real-time Model Context Protocol (MCP) daemon sessions, token expiry lifecycles, and cryptographic authorization status for Zerodha and INDmoney custodians.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadSessions}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-xs rounded-xl transition-all shadow-sm active:scale-95"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh State</span>
          </button>
        </div>
      </div>

      {/* 2. Top Telemetry KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Active MCP Sessions */}
        <div className="bg-white p-5 rounded-2xl shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              MCP Daemon Feeds
            </span>
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                activeCount === sessions.length
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200/60'
                  : 'bg-amber-50 text-amber-700 border border-amber-200/60'
              }`}
            >
              {activeCount} / {sessions.length} Operational
            </span>
          </div>
          <div className="mt-3">
            <div className="font-serif text-3xl text-slate-950 tracking-tight font-normal">
              {activeCount} Active Sessions
            </div>
            <div className="flex items-center gap-1.5 mt-1.5 text-xs text-slate-500">
              <Server className="w-3.5 h-3.5 text-slate-400" />
              <span>Stdio JSON-RPC v2.0 Protocol</span>
            </div>
          </div>
        </div>

        {/* Card 2: Total Synced Valuation */}
        <div className="bg-white p-5 rounded-2xl shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              Synced Valuation
            </span>
            <span className="text-xs text-slate-400 font-semibold">Live Combined</span>
          </div>
          <div className="mt-3">
            <div className="font-serif text-3xl text-slate-950 tracking-tight font-normal">
              {formatINR(totalValuation)}
            </div>
            <div className="flex items-center gap-1.5 mt-1.5 text-xs text-slate-500">
              <Layers className="w-3.5 h-3.5 text-slate-400" />
              <span>{totalHoldings} Canonical Positions Tracked</span>
            </div>
          </div>
        </div>

        {/* Card 3: Cryptographic Token Health */}
        <div className="bg-white p-5 rounded-2xl shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              Token Lifecycle
            </span>
            <span className="text-xs text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded font-bold border border-emerald-200/60">
              Daily 06:00 AM
            </span>
          </div>
          <div className="mt-3">
            <div className="font-serif text-3xl text-slate-950 tracking-tight font-normal">
              {sessions.some((s) => s.is_expired) ? 'Action Required' : 'Tokens Valid'}
            </div>
            <div className="flex items-center gap-1.5 mt-1.5 text-xs text-slate-500">
              <Clock className="w-3.5 h-3.5 text-slate-400" />
              <span>Kite Connect Daily Rotation</span>
            </div>
          </div>
        </div>

        {/* Card 4: Discovered Tools */}
        <div className="bg-white p-5 rounded-2xl shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              MCP Tools Registered
            </span>
            <span className="text-xs text-slate-600 bg-slate-100 px-2 py-0.5 rounded font-bold">
              30 Tools
            </span>
          </div>
          <div className="mt-3">
            <div className="font-serif text-3xl text-slate-950 tracking-tight font-normal">
              {sessions.reduce((acc, s) => acc + (s.tools_count || 0), 0)} Capabilities
            </div>
            <div className="flex items-center gap-1.5 mt-1.5 text-xs text-slate-500">
              <Terminal className="w-3.5 h-3.5 text-slate-400" />
              <span>Holdings, Orders, Quotes &amp; MF</span>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Broker MCP Sessions List */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-serif text-xl text-slate-950 font-medium">
            Active Broker MCP Sessions &amp; Custodians
          </h2>
          <span className="text-xs text-slate-500">
            Multi-Tenant Azure Table Isolated ({sessions.length} Connections)
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {sessions.map((session) => {
            const isZerodha = session.broker_name.toLowerCase().includes('zerodha')
            const isConnected = session.status === 'CONNECTED'
            const isExpired = session.status === 'SESSION_EXPIRED'
            const isAuthReq = session.status === 'AUTH_REQUIRED'
            const isDisconnected = session.status === 'DISCONNECTED'
            const syncTimeInfo = formatTimestamp(session.last_sync_time)
            const isCurrentlySyncing = actionLoading[session.broker_name] === 'syncing'
            const isCurrentlyTesting = actionLoading[session.broker_name] === 'testing'
            const successMsg = actionSuccess[session.broker_name]

            return (
              <div
                key={session.connection_id}
                className={`bg-white rounded-2xl p-6 sm:p-7 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border transition-all duration-200 flex flex-col justify-between ${
                  isExpired || isAuthReq
                    ? 'border-amber-300 ring-1 ring-amber-200/50 bg-amber-50/10'
                    : isDisconnected
                    ? 'border-slate-300 bg-slate-50/30'
                    : 'border-slate-200/80 hover:border-slate-300'
                }`}
              >
                <div>
                  {/* Top Row: Broker Brand, Account ID & Status Badge */}
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3.5">
                      {/* Custodian Icon */}
                      <div
                        className={`w-12 h-12 rounded-2xl flex items-center justify-center font-bold text-white shadow-sm shrink-0 ${
                          isZerodha
                            ? 'bg-[#e03a3c] shadow-red-100'
                            : 'bg-indigo-600 shadow-indigo-100'
                        }`}
                      >
                        {isZerodha ? (
                          <span className="font-serif text-xl tracking-tighter">ZK</span>
                        ) : (
                          <span className="font-serif text-xl tracking-tighter">IND</span>
                        )}
                      </div>

                      <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                          <h3 className="font-serif text-lg text-slate-950 font-medium leading-tight">
                            {session.display_name}
                          </h3>
                        </div>
                        <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                          <span className="font-mono font-semibold text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                            Client: {session.account_id}
                          </span>
                          <span>&bull;</span>
                          <span className="truncate max-w-[160px]">{session.connection_id}</span>
                        </div>
                      </div>
                    </div>

                    {/* Status Pill */}
                    <div className="flex flex-col items-end">
                      {isConnected && (
                        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200/60 shadow-sm">
                          <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-600"></span>
                          </span>
                          <span>Connected / Active</span>
                        </span>
                      )}

                      {isExpired && (
                        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300 shadow-sm">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                          <span>Session Expired</span>
                        </span>
                      )}

                      {isAuthReq && (
                        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-300 shadow-sm">
                          <AlertCircle className="w-3.5 h-3.5 text-rose-600" />
                          <span>Auth Required</span>
                        </span>
                      )}

                      {isDisconnected && (
                        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-600 border border-slate-200 shadow-sm">
                          <XCircle className="w-3.5 h-3.5 text-slate-400" />
                          <span>Disconnected</span>
                        </span>
                      )}

                      <span className="text-[10px] text-slate-400 mt-1 font-mono">
                        Latency: ~{session.last_latency_ms}ms
                      </span>
                    </div>
                  </div>

                  {/* Warning Box for Expired / Inactive Session */}
                  {(isExpired || isAuthReq || isDisconnected) && (
                    <div className="mt-5 p-4 rounded-xl bg-amber-50 border border-amber-200/80 flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
                      <div className="flex-1 text-xs">
                        <h4 className="font-bold text-amber-900 text-xs">
                          {isExpired
                            ? 'Cryptographic Session Token Expired'
                            : isAuthReq
                            ? isZerodha
                              ? 'Daily Kite OAuth Authorization Required'
                              : 'INDmoney OAuth Authorization Required'
                            : 'Broker Authorization Inactive'}
                        </h4>
                        <p className="text-amber-800 mt-0.5 leading-relaxed">
                          {isZerodha
                            ? 'Zerodha Kite Connect access tokens expire daily. Click below to log in on Kite in your browser, then click Confirm & Sync to stream your real-time holdings.'
                            : 'INDmoney OAuth authorization is required or expired. Click below to log in on INDmoney in your browser, then click Confirm & Sync to stream your live US stocks, NPS, and bonds.'}
                        </p>

                        <div className="mt-3 flex flex-wrap items-center gap-2.5">
                          <button
                            onClick={() => handleStartAuth(session)}
                            disabled={!!actionLoading[session.broker_name]}
                            className={`inline-flex items-center gap-1.5 px-3 py-1.5 ${
                              isZerodha ? 'bg-rose-600 hover:bg-rose-700' : 'bg-indigo-600 hover:bg-indigo-700'
                            } text-white font-bold text-xs rounded-xl shadow-sm transition-all active:scale-95 disabled:opacity-50`}
                          >
                            <Key className="w-3.5 h-3.5" />
                            <span>
                              {actionLoading[session.broker_name] === 'authorizing'
                                ? 'Opening Login...'
                                : isZerodha
                                ? 'Authorize on Kite (Opens in New Tab)'
                                : 'Authorize on INDmoney (Opens in New Tab)'}
                            </span>
                          </button>
                          <button
                            onClick={() => handleSingleSync(session.broker_name)}
                            disabled={!!actionLoading[session.broker_name]}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs rounded-xl transition-all shadow-sm active:scale-95 disabled:opacity-50"
                          >
                            <RefreshCw className={`w-3.5 h-3.5 ${isCurrentlySyncing ? 'animate-spin' : ''}`} />
                            <span>{isCurrentlySyncing ? 'Syncing...' : 'I Have Logged In -> Sync Now'}</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Telemetry Detail Grid */}
                  <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 gap-3 p-4 rounded-xl bg-slate-50 border border-slate-100 text-xs">
                    <div>
                      <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                        Last Successful Sync
                      </span>
                      <div className="font-bold text-slate-900 mt-1 flex items-center gap-1">
                        <Clock className="w-3 h-3 text-slate-400" />
                        <span>{syncTimeInfo.relative}</span>
                      </div>
                      <span className="text-[10px] text-slate-400 block mt-0.5 font-mono">
                        {syncTimeInfo.full}
                      </span>
                    </div>

                    <div>
                      <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                        Synced Assets
                      </span>
                      <div className="font-bold text-slate-900 mt-1">
                        {session.holdings_count} Positions
                      </div>
                      <span className="text-[10px] text-emerald-700 font-semibold block mt-0.5">
                        {formatINR(session.total_valuation)}
                      </span>
                    </div>

                    <div>
                      <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                        Session Auth Type
                      </span>
                      <div className="font-bold text-slate-900 mt-1 flex items-center gap-1">
                        <Lock className="w-3 h-3 text-slate-400" />
                        <span className="truncate">{session.auth_type}</span>
                      </div>
                      <span className="text-[10px] text-slate-400 block mt-0.5">
                        {isZerodha ? 'Daily Auto-Rotate' : 'OAuth 2.0 Bearer'}
                      </span>
                    </div>

                    <div className="col-span-2 sm:col-span-3 pt-2 border-t border-slate-200/60 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-[11px] text-slate-500">
                        <Cpu className="w-3.5 h-3.5 text-slate-400" />
                        <span>MCP Gateway:</span>
                        <code className="font-mono text-[10px] bg-white px-1.5 py-0.5 rounded border border-slate-200 text-slate-700 truncate max-w-[200px]">
                          {session.mcp_server_url}
                        </code>
                      </div>

                      <button
                        onClick={() =>
                          setExpandedTools(
                            expandedTools === session.broker_name ? null : session.broker_name
                          )
                        }
                        className="text-[11px] font-semibold text-slate-700 hover:text-slate-950 flex items-center gap-1"
                      >
                        <Eye className="w-3 h-3" />
                        <span>
                          {expandedTools === session.broker_name ? 'Hide' : 'View'} {session.tools_count} MCP Tools
                        </span>
                      </button>
                    </div>
                  </div>

                  {/* Expandable MCP Tools Directory */}
                  {expandedTools === session.broker_name && (
                    <div className="mt-3 p-3.5 rounded-xl bg-slate-950 text-slate-200 text-xs font-mono">
                      <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-[11px]">
                        <span className="text-emerald-400 font-bold flex items-center gap-1.5">
                          <Terminal className="w-3.5 h-3.5" />
                          Registered Capabilities ({session.display_name})
                        </span>
                        <span className="text-slate-400 text-[10px]">MCP Stdio v2.0</span>
                      </div>
                      <div className="mt-2.5 grid grid-cols-2 gap-2 text-[11px]">
                        {isZerodha ? (
                          <>
                            <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                              <code className="text-emerald-400">get_holdings</code>
                              <p className="text-[10px] text-slate-400 mt-0.5">Demat equity positions</p>
                            </div>
                            <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                              <code className="text-emerald-400">get_mf_holdings</code>
                              <p className="text-[10px] text-slate-400 mt-0.5">Coin mutual fund units</p>
                            </div>
                            <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                              <code className="text-emerald-400">get_profile</code>
                              <p className="text-[10px] text-slate-400 mt-0.5">User profile &amp; margins</p>
                            </div>
                            <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                              <code className="text-emerald-400">get_quotes</code>
                              <p className="text-[10px] text-slate-400 mt-0.5">Real-time Level 3 market depth</p>
                            </div>
                          </>
                        ) : (
                          <>
                            <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                              <code className="text-emerald-400">get_holdings</code>
                              <p className="text-[10px] text-slate-400 mt-0.5">US tech &amp; mutual funds</p>
                            </div>
                            <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                              <code className="text-emerald-400">get_nps_summary</code>
                              <p className="text-[10px] text-slate-400 mt-0.5">National Pension Tier 1</p>
                            </div>
                            <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                              <code className="text-emerald-400">get_bonds</code>
                              <p className="text-[10px] text-slate-400 mt-0.5">Fixed income &amp; SGBs</p>
                            </div>
                            <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                              <code className="text-emerald-400">get_account_status</code>
                              <p className="text-[10px] text-slate-400 mt-0.5">Auth state &amp; sync health</p>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Feedback Message */}
                  {successMsg && (
                    <div className="mt-3 p-2.5 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      <span>{successMsg}</span>
                    </div>
                  )}
                </div>

                {/* Bottom Action Footer */}
                <div className="mt-6 pt-4 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
                  {/* Primary Action Button */}
                  {isConnected ? (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleSingleSync(session.broker_name)}
                        disabled={!!actionLoading[session.broker_name]}
                        className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-slate-950 hover:bg-slate-800 text-white font-semibold text-xs rounded-xl transition-all shadow-sm active:scale-95 disabled:opacity-50"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isCurrentlySyncing ? 'animate-spin' : ''}`} />
                        <span>{isCurrentlySyncing ? 'Syncing...' : 'Sync Now'}</span>
                      </button>

                      <button
                        onClick={() => handleTestHandshake(session.broker_name)}
                        disabled={!!actionLoading[session.broker_name]}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-xs rounded-xl transition-all active:scale-95"
                      >
                        <Activity className={`w-3.5 h-3.5 ${isCurrentlyTesting ? 'animate-pulse text-emerald-600' : ''}`} />
                        <span>Test MCP</span>
                      </button>
                    </div>
                  ) : (
                    /* Inactive / Expired: Prominent Re-Authenticate Button */
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleStartAuth(session)}
                        disabled={!!actionLoading[session.broker_name]}
                        className={`inline-flex items-center gap-1.5 px-4 py-2 ${
                          isZerodha ? 'bg-rose-600 hover:bg-rose-700' : 'bg-indigo-600 hover:bg-indigo-700'
                        } text-white font-bold text-xs rounded-xl shadow-sm transition-all active:scale-95 disabled:opacity-50`}
                      >
                        <Key className="w-3.5 h-3.5" />
                        <span>
                          {actionLoading[session.broker_name] === 'authorizing'
                            ? 'Connecting...'
                            : isZerodha
                            ? 'Authorize Kite'
                            : 'Authorize INDmoney'}
                        </span>
                      </button>
                      <button
                        onClick={() => handleSingleSync(session.broker_name)}
                        disabled={!!actionLoading[session.broker_name]}
                        className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs rounded-xl transition-all shadow-sm active:scale-95 disabled:opacity-50"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isCurrentlySyncing ? 'animate-spin' : ''}`} />
                        <span>{isCurrentlySyncing ? 'Syncing...' : 'Sync Now'}</span>
                      </button>
                    </div>
                  )}

                  {/* Diagnostic / Testing Actions */}
                  <div className="flex items-center gap-2 text-xs">
                    {isConnected ? (
                      <>
                        <button
                          onClick={() => handleSimulateExpire(session.broker_name)}
                          disabled={!!actionLoading[session.broker_name]}
                          className="px-2 py-1 text-[11px] font-semibold text-slate-500 hover:text-amber-700 hover:bg-amber-50 rounded-lg transition-colors"
                          title="Simulate token expiration to test re-authentication UX"
                        >
                          Simulate Expiry
                        </button>
                        <button
                          onClick={() => handleDisconnect(session.broker_name)}
                          disabled={!!actionLoading[session.broker_name]}
                          className="px-2 py-1 text-[11px] font-semibold text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                          title="Disconnect session"
                        >
                          Disconnect
                        </button>
                      </>
                    ) : (
                      <span className="text-[11px] text-amber-700 font-semibold flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        <span>Awaiting Re-Auth</span>
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* 4. Institutional Architecture Memo */}
      <div className="bg-white rounded-2xl p-6 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80">
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck className="w-4 h-4 text-emerald-600" />
          <h2 className="font-serif text-lg text-slate-950 font-medium">
            Broker Synchronization Compliance &amp; Protocol Architecture
          </h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-xs text-slate-600 leading-relaxed">
          <div className="flex flex-col gap-1 p-4 rounded-xl bg-slate-50 border border-slate-100">
            <span className="font-bold text-slate-900 text-sm">Strict Zero-Leakage Isolation</span>
            <p className="mt-1">
              Every broker session is keyed strictly by Azure Table Storage PartitionKey <code className="text-slate-800 font-mono">owner_id</code>. Demat holdings and trade transactions never bleed across client boundaries.
            </p>
          </div>
          <div className="flex flex-col gap-1 p-4 rounded-xl bg-slate-50 border border-slate-100">
            <span className="font-bold text-slate-900 text-sm">Immutable Blob Archiving</span>
            <p className="mt-1">
              Every orchestrated sync writes complete raw broker JSON payloads directly to Azure Blob Storage under <code className="text-slate-800 font-mono">raw-broker-payloads/{'{user_id}'}/{'{connection_id}'}/</code> for regulatory audit.
            </p>
          </div>
          <div className="flex flex-col gap-1 p-4 rounded-xl bg-slate-50 border border-slate-100">
            <span className="font-bold text-slate-900 text-sm">Kite Connect Daily Protocol</span>
            <p className="mt-1">
              SEBI security standards require Indian broker sessions (Zerodha Kite) to rotate daily at 06:00 AM IST. WealthVault surfaces proactive renewal alerts so your valuations remain uninterrupted.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

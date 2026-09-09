import React, { useState, useEffect } from 'react'
import {
  Radio,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Key,
  Lock,
  Cpu,
  AlertCircle,
  Eye,
  Layers,
  Server,
  Terminal,
  Plus,
  Search,
  Check,
  Trash2,
  Building2,
  X,
} from 'lucide-react'
import {
  fetchBrokerSessions,
  syncBroker,
  fetchBrokerCatalog,
  addBrokerConnection,
  deleteBrokerConnection,
} from '../utils/api'
import type { BrokerCatalogItem, BrokerSessionInfo } from '../types'
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

  // Add Custodian Modal state
  const [showAddModal, setShowAddModal] = useState(false)
  const [catalog, setCatalog] = useState<BrokerCatalogItem[]>([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [addingBroker, setAddingBroker] = useState<string | null>(null)

  // Multi-account addition configuration state
  const [selectedBrokerForAdd, setSelectedBrokerForAdd] = useState<BrokerCatalogItem | null>(null)
  const [accountLabelInput, setAccountLabelInput] = useState('')
  const [accountIdInput, setAccountIdInput] = useState('')

  // Remove Broker & Wipe Data Modal state
  const [removeModalSession, setRemoveModalSession] = useState<BrokerSessionInfo | null>(null)
  const [wipeBlobs, setWipeBlobs] = useState(true)
  const [isWiping, setIsWiping] = useState(false)

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

  const loadCatalog = async () => {
    try {
      setCatalogLoading(true)
      const data = await fetchBrokerCatalog()
      setCatalog(data)
    } catch (err) {
      console.error('Failed to load broker catalog:', err)
    } finally {
      setCatalogLoading(false)
    }
  }

  const openConnectForm = (brokerItem: BrokerCatalogItem) => {
    setSelectedBrokerForAdd(brokerItem)
    const existingForBroker = sessions.filter(
      (s) => s.broker_name.toLowerCase() === brokerItem.broker_name.toLowerCase()
    )
    if (existingForBroker.length > 0) {
      setAccountLabelInput(`Account ${existingForBroker.length + 1}`)
    } else {
      setAccountLabelInput(
        brokerItem.broker_name === 'zerodha'
          ? 'Personal Demat'
          : brokerItem.broker_name === 'indmoney'
          ? 'Primary Wealth'
          : 'Primary Account'
      )
    }
    setAccountIdInput('')
  }

  const handleAddBroker = async (brokerItem: BrokerCatalogItem) => {
    setAddingBroker(brokerItem.broker_name)
    try {
      const newSession = await addBrokerConnection({
        broker_name: brokerItem.broker_name,
        account_label: accountLabelInput.trim() || undefined,
        account_id: accountIdInput.trim() || undefined,
      })
      await loadSessions()
      await loadCatalog()
      if (newSession.auth_url) {
        window.open(newSession.auth_url, '_blank')
      }
      setShowAddModal(false)
      setSelectedBrokerForAdd(null)
      setActionSuccess((prev) => ({
        ...prev,
        [newSession.connection_id]: `${newSession.display_name} connected successfully.`,
      }))
      setTimeout(() => {
        setActionSuccess((prev) => ({ ...prev, [newSession.connection_id]: null }))
      }, 4000)
    } catch (err: any) {
      alert(`Failed to add connection: ${err.message}`)
    } finally {
      setAddingBroker(null)
    }
  }

  const handleConfirmWipe = async () => {
    if (!removeModalSession) return
    const connId = removeModalSession.connection_id
    const displayName = removeModalSession.display_name
    setIsWiping(true)
    try {
      const res = await deleteBrokerConnection(connId, wipeBlobs)
      setRemoveModalSession(null)
      await loadSessions()
      await loadCatalog()
      await refreshPortfolio()
      setActionSuccess((prev) => ({
        ...prev,
        [connId]: `${displayName} disconnected: ${res.holdings_purged} holdings purged. Net worth updated.`,
      }))
      setTimeout(() => {
        setActionSuccess((prev) => ({ ...prev, [connId]: null }))
      }, 5000)
    } catch (err: any) {
      alert(`Failed to remove broker: ${err.message}`)
    } finally {
      setIsWiping(false)
    }
  }

  const getBrokerBrand = (name: string) => {
    const n = name.toLowerCase()
    if (n.includes('zerodha')) return { tag: 'ZK', color: 'bg-[#e03a3c]', shadow: 'shadow-red-100', text: 'text-[#e03a3c]' }
    if (n.includes('indmoney')) return { tag: 'IND', color: 'bg-indigo-600', shadow: 'shadow-indigo-100', text: 'text-indigo-600' }
    if (n.includes('groww')) return { tag: 'GRW', color: 'bg-emerald-600', shadow: 'shadow-emerald-100', text: 'text-emerald-600' }
    if (n.includes('upstox')) return { tag: 'UPX', color: 'bg-purple-600', shadow: 'shadow-purple-100', text: 'text-purple-600' }
    if (n.includes('angel')) return { tag: 'ANG', color: 'bg-orange-600', shadow: 'shadow-orange-100', text: 'text-orange-600' }
    if (n.includes('dhan')) return { tag: 'DHN', color: 'bg-blue-600', shadow: 'shadow-blue-100', text: 'text-blue-600' }
    if (n.includes('icici')) return { tag: 'ICI', color: 'bg-amber-600', shadow: 'shadow-amber-100', text: 'text-amber-600' }
    if (n.includes('hdfc')) return { tag: 'SKY', color: 'bg-sky-600', shadow: 'shadow-sky-100', text: 'text-sky-600' }
    return { tag: n.slice(0, 3).toUpperCase(), color: 'bg-slate-800', shadow: 'shadow-slate-100', text: 'text-slate-800' }
  }

  useEffect(() => {
    loadSessions()

    const handleMessage = (event: MessageEvent) => {
      if (event.data === 'indmoney_authorized') {
        loadSessions()
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

  const handleSingleSync = async (session: BrokerSessionInfo) => {
    const connId = session.connection_id
    setActionLoading((prev) => ({ ...prev, [connId]: 'syncing' }))
    try {
      const updated = await syncBroker(connId)
      setSessions((prev) => prev.map((s) => (s.connection_id === connId ? updated : s)))

      if (updated.status === 'AUTH_REQUIRED' || updated.status === 'SESSION_EXPIRED') {
        alert(
          `${updated.display_name} authorization is required. Please click 'Authorize' to log in in your browser, then click Sync again.`
        )
      } else if (updated.status === 'CONNECTED') {
        await refreshPortfolio()
        setActionSuccess((prev) => ({
          ...prev,
          [connId]: `Synced successfully! ${updated.holdings_count} positions updated.`,
        }))
        setTimeout(() => {
          setActionSuccess((prev) => ({ ...prev, [connId]: null }))
        }, 4000)
      }
    } catch (err: any) {
      alert(`Sync failed: ${err.message}`)
    } finally {
      setActionLoading((prev) => ({ ...prev, [connId]: null }))
    }
  }

  const handleStartAuth = async (session: BrokerSessionInfo) => {
    const connId = session.connection_id
    if (session.auth_url) {
      window.open(session.auth_url, '_blank')
      return
    }
    setActionLoading((prev) => ({ ...prev, [connId]: 'authorizing' }))
    try {
      // 1. Refresh sessions to fetch the latest auth_url generated by backend
      const fresh = await fetchBrokerSessions()
      setSessions(fresh)
      const target = fresh.find((s) => s.connection_id === connId)
      if (target?.auth_url) {
        window.open(target.auth_url, '_blank')
        return
      }

      // 2. Fallback: call sync endpoint which forces session re-init & acquires fresh auth_url
      const synced = await syncBroker(connId)
      setSessions((prev) => prev.map((s) => (s.connection_id === connId ? synced : s)))
      if (synced?.auth_url) {
        window.open(synced.auth_url, '_blank')
      } else {
        alert(`Could not retrieve authorization link for ${session.display_name}.`)
      }
    } catch (err: any) {
      alert(`Could not start authorization: ${err.message}`)
    } finally {
      setActionLoading((prev) => ({ ...prev, [connId]: null }))
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

      {/* Top Telemetry KPI Cards */}
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

        {/* Card 4: System Gateway & Refresh State */}
        <div className="bg-white p-5 rounded-2xl shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              System Gateway
            </span>
            <span className="inline-flex items-center gap-1 text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded font-bold border border-emerald-200/60">
              <Radio className="w-2.5 h-2.5 animate-pulse" />
              <span>Live Mesh</span>
            </span>
          </div>
          <div className="mt-3">
            <button
              onClick={loadSessions}
              disabled={loading}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-950 hover:bg-slate-800 text-white font-semibold text-xs rounded-xl transition-all shadow-sm active:scale-95 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>{loading ? 'Refreshing State...' : 'Refresh State'}</span>
            </button>
            <div className="flex items-center justify-center gap-1.5 mt-2 text-[11px] text-slate-400">
              <Server className="w-3 h-3 text-slate-400" />
              <span>Poll MCP Session Gateways</span>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Broker MCP Sessions List */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="font-serif text-xl text-slate-950 font-medium">
              Active Broker MCP Sessions &amp; Custodians
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Multi-Tenant Azure Table Isolated &bull; {sessions.length} Connections Configured
            </p>
          </div>
          <button
            onClick={() => {
              setShowAddModal(true)
              loadCatalog()
            }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-950 hover:bg-slate-800 text-white font-semibold text-xs rounded-xl transition-all shadow-sm active:scale-95 shrink-0 cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>Add Broker Connection</span>
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {sessions.map((session) => {
            const isZerodha = session.broker_name.toLowerCase().includes('zerodha')
            const brand = getBrokerBrand(session.broker_name)
            const isConnected = session.status === 'CONNECTED'
            const isExpired = session.status === 'SESSION_EXPIRED'
            const isAuthReq = session.status === 'AUTH_REQUIRED'
            const isDisconnected = session.status === 'DISCONNECTED'
            const syncTimeInfo = formatTimestamp(session.last_sync_time)
            const isCurrentlySyncing = actionLoading[session.connection_id] === 'syncing'
            const successMsg = actionSuccess[session.connection_id]

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
                        className={`w-12 h-12 rounded-2xl flex items-center justify-center font-bold text-white shadow-sm shrink-0 ${brand.color} ${brand.shadow}`}
                      >
                        <span className="font-serif text-xl tracking-tighter">{brand.tag}</span>
                      </div>

                      <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                          <h3 className="font-serif text-lg text-slate-950 font-medium leading-tight">
                            {session.display_name}
                          </h3>
                          {session.account_label && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200/60">
                              {session.account_label}
                            </span>
                          )}
                          <button
                            onClick={() => setRemoveModalSession(session)}
                            className="text-slate-300 hover:text-rose-600 hover:bg-rose-50 p-1 rounded-lg transition-colors cursor-pointer"
                            title={`Remove ${session.display_name} and wipe data`}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
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
                            disabled={!!actionLoading[session.connection_id]}
                            className={`inline-flex items-center gap-1.5 px-3 py-1.5 ${
                              isZerodha ? 'bg-rose-600 hover:bg-rose-700' : 'bg-indigo-600 hover:bg-indigo-700'
                            } text-white font-bold text-xs rounded-xl shadow-sm transition-all active:scale-95 disabled:opacity-50`}
                          >
                            <Key className="w-3.5 h-3.5" />
                            <span>
                              {actionLoading[session.connection_id] === 'authorizing'
                                ? 'Opening Login...'
                                : isZerodha
                                ? 'Authorize on Kite (Opens in New Tab)'
                                : 'Authorize on INDmoney (Opens in New Tab)'}
                            </span>
                          </button>
                          <button
                            onClick={() => handleSingleSync(session)}
                            disabled={!!actionLoading[session.connection_id]}
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
                            expandedTools === session.connection_id ? null : session.connection_id
                          )
                        }
                        className="text-[11px] font-semibold text-slate-700 hover:text-slate-950 flex items-center gap-1"
                      >
                        <Eye className="w-3 h-3" />
                        <span>
                          {expandedTools === session.connection_id ? 'Hide' : 'View'} {session.tools_count} MCP Tools
                        </span>
                      </button>
                    </div>
                  </div>

                  {/* Expandable MCP Tools Directory */}
                  {expandedTools === session.connection_id && (
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
                        onClick={() => handleSingleSync(session)}
                        disabled={!!actionLoading[session.connection_id]}
                        className="inline-flex items-center gap-1.5 px-4 py-2 bg-slate-950 hover:bg-slate-800 text-white font-semibold text-xs rounded-xl transition-all shadow-sm active:scale-95 disabled:opacity-50 cursor-pointer"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isCurrentlySyncing ? 'animate-spin' : ''}`} />
                        <span>{isCurrentlySyncing ? 'Syncing...' : 'Sync Now'}</span>
                      </button>
                      <button
                        onClick={() => setRemoveModalSession(session)}
                        className="inline-flex items-center gap-1.5 px-3 py-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 text-xs font-semibold rounded-xl transition-all cursor-pointer"
                        title={`Remove ${session.display_name} and wipe data`}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">Remove</span>
                      </button>
                    </div>
                  ) : (
                    /* Inactive / Expired: Prominent Re-Authenticate Button */
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleStartAuth(session)}
                        disabled={!!actionLoading[session.connection_id]}
                        className={`inline-flex items-center gap-1.5 px-4 py-2 ${
                          isZerodha ? 'bg-rose-600 hover:bg-rose-700' : 'bg-indigo-600 hover:bg-indigo-700'
                        } text-white font-bold text-xs rounded-xl shadow-sm transition-all active:scale-95 disabled:opacity-50 cursor-pointer`}
                      >
                        <Key className="w-3.5 h-3.5" />
                        <span>
                          {actionLoading[session.connection_id] === 'authorizing'
                            ? 'Connecting...'
                            : isZerodha
                            ? 'Authorize Kite'
                            : 'Authorize INDmoney'}
                        </span>
                      </button>
                      <button
                        onClick={() => handleSingleSync(session)}
                        disabled={!!actionLoading[session.connection_id]}
                        className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs rounded-xl transition-all shadow-sm active:scale-95 disabled:opacity-50 cursor-pointer"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isCurrentlySyncing ? 'animate-spin' : ''}`} />
                        <span>{isCurrentlySyncing ? 'Syncing...' : 'Sync Now'}</span>
                      </button>
                      <button
                        onClick={() => setRemoveModalSession(session)}
                        className="inline-flex items-center gap-1.5 px-3 py-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 text-xs font-semibold rounded-xl transition-all cursor-pointer"
                        title={`Remove ${session.display_name} and wipe data`}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">Remove</span>
                      </button>
                    </div>
                  )}

                  {/* Status Indicator */}
                  <div className="flex items-center gap-2 text-xs">
                    {isConnected ? (
                      <span className="text-[11px] text-slate-500 font-mono flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                        <span>Synced {syncTimeInfo.relative}</span>
                      </span>
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

          {/* Card: Connect Another Custodian */}
          <button
            onClick={() => {
              setShowAddModal(true)
              loadCatalog()
            }}
            className="border-2 border-dashed border-slate-300 hover:border-slate-900/60 bg-slate-50/50 hover:bg-white rounded-2xl p-7 flex flex-col items-center justify-center text-center transition-all duration-200 group min-h-[280px] cursor-pointer shadow-none hover:shadow-sm"
          >
            <div className="w-14 h-14 rounded-2xl bg-white group-hover:bg-slate-950 text-slate-400 group-hover:text-white border border-slate-200 group-hover:border-slate-950 flex items-center justify-center transition-all shadow-sm">
              <Plus className="w-6 h-6 stroke-[2.5]" />
            </div>
            <h3 className="font-serif text-lg font-medium text-slate-950 mt-4">
              Connect Another Custodian
            </h3>
            <p className="text-xs text-slate-500 max-w-xs mt-1.5 leading-relaxed">
              Link Groww, Upstox, Angel One, Dhan, ICICI Direct, HDFC Sky, or other Indian &amp; Global Demat ledgers.
            </p>
            <span className="mt-4 inline-flex items-center gap-1.5 text-xs font-bold text-slate-900 group-hover:underline">
              <span>Browse Custodian Catalog</span>
              <span>&rarr;</span>
            </span>
          </button>
        </div>
      </div>

      {/* 4. Add Broker Custodian Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/40 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200/80 w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-700">
                  <Building2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-serif text-xl font-medium text-slate-950">
                    Connect Broker Custodian
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Select an institutional custodian to link directly into your WealthVault private vault
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowAddModal(false)}
                className="p-2 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Search Bar */}
            {!selectedBrokerForAdd && (
              <div className="px-6 py-3 border-b border-slate-100 bg-slate-50/50">
                <div className="relative">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search broker custodians (e.g. Zerodha, Groww, Upstox, Dhan, INDmoney)..."
                    className="w-full pl-10 pr-4 py-2 text-xs bg-white rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-950 text-slate-900 placeholder:text-slate-400"
                  />
                </div>
              </div>
            )}

            {/* Modal Catalog Body */}
            <div className="p-6 overflow-y-auto flex-1 space-y-3">
              {selectedBrokerForAdd ? (
                /* Multi-Account Configuration Form */
                <div className="space-y-4 animate-in fade-in duration-150">
                  <button
                    type="button"
                    onClick={() => setSelectedBrokerForAdd(null)}
                    className="text-xs font-semibold text-slate-500 hover:text-slate-900 flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <span>&larr;</span>
                    <span>Back to Custodian Catalog</span>
                  </button>

                  <div className="flex items-center gap-3.5 p-4 rounded-xl bg-slate-50 border border-slate-200/80">
                    <div
                      className={`w-11 h-11 rounded-xl flex items-center justify-center font-bold text-white shadow-sm shrink-0 ${
                        getBrokerBrand(selectedBrokerForAdd.broker_name).color
                      }`}
                    >
                      {getBrokerBrand(selectedBrokerForAdd.broker_name).tag}
                    </div>
                    <div>
                      <h3 className="font-serif text-base font-semibold text-slate-950">
                        Add {selectedBrokerForAdd.display_name} Account
                      </h3>
                      <p className="text-xs text-slate-500">
                        Multi-Account isolation &bull; Dedicated credentials &amp; isolated sync
                      </p>
                    </div>
                  </div>

                  <form
                    onSubmit={(e) => {
                      e.preventDefault()
                      handleAddBroker(selectedBrokerForAdd)
                    }}
                    className="space-y-4 pt-1"
                  >
                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1.5">
                        Account Alias / Label
                      </label>
                      <input
                        type="text"
                        value={accountLabelInput}
                        onChange={(e) => setAccountLabelInput(e.target.value)}
                        placeholder="e.g. Personal Demat, Family HUF, Spouse Wealth"
                        className="w-full px-3.5 py-2.5 text-xs bg-white rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-950 text-slate-900 placeholder:text-slate-400 shadow-sm"
                      />
                      <span className="text-[11px] text-slate-400 mt-1 block">
                        Differentiates this connection card from your other {selectedBrokerForAdd.display_name} accounts.
                      </span>
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-slate-700 mb-1.5">
                        Account / Demat / Client ID <span className="text-slate-400 font-normal">(Optional)</span>
                      </label>
                      <input
                        type="text"
                        value={accountIdInput}
                        onChange={(e) => setAccountIdInput(e.target.value)}
                        placeholder={
                          selectedBrokerForAdd.broker_name === 'zerodha'
                            ? 'e.g. SRK113 or Demat Client ID'
                            : 'e.g. Client / User Identifier'
                        }
                        className="w-full px-3.5 py-2.5 text-xs bg-white rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-950 text-slate-900 placeholder:text-slate-400 shadow-sm"
                      />
                    </div>

                    <div className="p-3.5 rounded-xl bg-indigo-50/70 border border-indigo-100 text-xs text-indigo-900 flex items-start gap-2.5">
                      <Server className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                      <div className="leading-relaxed">
                        <b>Independent Ledger:</b> A discrete connection will be provisioned in your vault. Holdings will remain segregated per account while automatically rolling up into your consolidated Net Worth.
                      </div>
                    </div>

                    <div className="pt-3 flex items-center justify-end gap-2.5 border-t border-slate-100">
                      <button
                        type="button"
                        onClick={() => setSelectedBrokerForAdd(null)}
                        className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-xl transition-colors cursor-pointer"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={addingBroker === selectedBrokerForAdd.broker_name}
                        className="inline-flex items-center gap-2 px-5 py-2 bg-slate-950 hover:bg-slate-800 text-white font-bold text-xs rounded-xl transition-all shadow-sm active:scale-95 disabled:opacity-50 cursor-pointer"
                      >
                        {addingBroker === selectedBrokerForAdd.broker_name ? (
                          <>
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            <span>Connecting Account...</span>
                          </>
                        ) : (
                          <>
                            <Plus className="w-3.5 h-3.5" />
                            <span>Connect &amp; Authorize Account</span>
                          </>
                        )}
                      </button>
                    </div>
                  </form>
                </div>
              ) : catalogLoading ? (
                <div className="py-12 flex flex-col items-center justify-center">
                  <RefreshCw className="w-6 h-6 animate-spin text-slate-400" />
                  <p className="text-xs text-slate-500 mt-2">Loading supported custodians...</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                  {catalog
                    .filter((item) => {
                      if (!searchQuery.trim()) return true
                      const q = searchQuery.toLowerCase()
                      return (
                        item.display_name.toLowerCase().includes(q) ||
                        item.broker_name.toLowerCase().includes(q) ||
                        item.description.toLowerCase().includes(q)
                      )
                    })
                    .map((item) => {
                      const brand = getBrokerBrand(item.broker_name)
                      const connectedCount =
                        item.connected_count ??
                        sessions.filter(
                          (s) => s.broker_name.toLowerCase() === item.broker_name.toLowerCase()
                        ).length
                      const isConnected = connectedCount > 0
                      const isConnecting = addingBroker === item.broker_name

                      return (
                        <div
                          key={item.broker_name}
                          className="p-4 rounded-xl border transition-all flex flex-col justify-between bg-white border-slate-200/80 hover:border-slate-400 hover:shadow-sm"
                        >
                          <div>
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex items-center gap-2.5">
                                <div
                                  className={`w-9 h-9 rounded-xl flex items-center justify-center font-bold text-white text-xs shrink-0 ${brand.color}`}
                                >
                                  {brand.tag}
                                </div>
                                <div>
                                  <h4 className="text-xs font-bold text-slate-950 font-serif">
                                    {item.display_name}
                                  </h4>
                                  <span className="text-[10px] text-slate-400 font-mono block">
                                    {item.mcp_protocol}
                                  </span>
                                </div>
                              </div>
                              {isConnected && (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200/60 shrink-0">
                                  <Check className="w-3 h-3 text-emerald-600" />
                                  <span>
                                    {connectedCount} {connectedCount === 1 ? 'Account' : 'Accounts'}
                                  </span>
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-600 mt-2.5 leading-relaxed">
                              {item.description}
                            </p>
                          </div>

                          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                            <span className="text-[10px] font-mono text-slate-400">
                              {item.auth_type}
                            </span>
                            <button
                              onClick={() => openConnectForm(item)}
                              disabled={isConnecting}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-950 hover:bg-slate-800 text-white font-bold text-xs rounded-xl transition-all shadow-sm active:scale-95 disabled:opacity-50 cursor-pointer"
                            >
                              {isConnecting ? (
                                <>
                                  <RefreshCw className="w-3 h-3 animate-spin" />
                                  <span>Linking...</span>
                                </>
                              ) : (
                                <>
                                  <Plus className="w-3.5 h-3.5" />
                                  <span>{isConnected ? '+ Add Another Account' : 'Connect'}</span>
                                </>
                              )}
                            </button>
                          </div>
                        </div>
                      )
                    })}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3.5 border-t border-slate-100 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
              <span className="flex items-center gap-1.5 text-[11px]">
                <Lock className="w-3.5 h-3.5 text-slate-400" />
                <span>Encrypted at rest &bull; Azure Table Partition Scoped</span>
              </span>
              <button
                onClick={() => setShowAddModal(false)}
                className="px-3.5 py-1.5 text-xs font-semibold text-slate-700 hover:text-slate-950 hover:bg-slate-200/60 rounded-xl transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. Remove Broker & Wipe Data Confirmation Modal */}
      {removeModalSession && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/50 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl shadow-2xl border border-rose-100 w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-rose-50/50">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-rose-100 flex items-center justify-center text-rose-700">
                  <Trash2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-serif text-lg font-medium text-slate-950">
                    Remove {removeModalSession.display_name}
                  </h3>
                  <p className="text-xs text-rose-700 font-medium mt-0.5">
                    Irreversible broker disconnection &amp; data wipeout
                  </p>
                </div>
              </div>
              <button
                onClick={() => setRemoveModalSession(null)}
                disabled={isWiping}
                className="p-2 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-white/80 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 space-y-4">
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 text-xs text-slate-700 space-y-2.5">
                <div className="font-bold text-slate-900 flex items-center justify-between pb-2 border-b border-slate-200">
                  <span>Custodian Connection</span>
                  <span className="font-mono text-[11px] text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200">
                    {removeModalSession.connection_id}
                  </span>
                </div>
                {removeModalSession.account_label && (
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Account Label / Alias:</span>
                    <span className="font-semibold text-slate-800">
                      {removeModalSession.account_label}
                    </span>
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Holdings to be purged:</span>
                  <span className="font-bold text-rose-700">
                    {removeModalSession.holdings_count} positions
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Valuation to be deducted:</span>
                  <span className="font-bold text-rose-700">
                    {formatINR(removeModalSession.total_valuation)}
                  </span>
                </div>
                <div className="flex items-center justify-between pt-2 border-t border-slate-200/60">
                  <span className="text-slate-500">Consolidated Net Worth:</span>
                  <span className="font-semibold text-slate-800">
                    Automatically recalculated
                  </span>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-2.5 text-xs text-amber-900">
                <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
                <span>
                  All canonical holding records associated with <b>{removeModalSession.display_name}</b> will be permanently wiped from your private vault database.
                </span>
              </div>

              {/* Blob Storage Wipe Option */}
              <label className="flex items-start gap-3 p-3 rounded-xl border border-slate-200 hover:bg-slate-50/70 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={wipeBlobs}
                  onChange={(e) => setWipeBlobs(e.target.checked)}
                  className="mt-0.5 rounded border-slate-300 text-rose-600 focus:ring-rose-500"
                />
                <div className="text-xs">
                  <span className="font-bold text-slate-900 block">
                    Purge archived raw JSON payloads
                  </span>
                  <span className="text-slate-500 text-[11px] mt-0.5 block">
                    Permanently delete raw JSON sync payloads stored in Azure Blob Storage under <code className="font-mono bg-slate-100 px-1 rounded">raw-broker-payloads/{removeModalSession.connection_id}</code>.
                  </span>
                </div>
              </label>
            </div>

            {/* Modal Actions */}
            <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 flex items-center justify-end gap-2.5">
              <button
                onClick={() => setRemoveModalSession(null)}
                disabled={isWiping}
                className="px-4 py-2 text-xs font-semibold text-slate-700 hover:text-slate-950 hover:bg-slate-200/60 rounded-xl transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmWipe}
                disabled={isWiping}
                className="inline-flex items-center gap-2 px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs rounded-xl transition-all shadow-sm active:scale-95 disabled:opacity-50 cursor-pointer"
              >
                {isWiping ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Wiping Data &amp; Disconnecting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Wipe Data &amp; Disconnect</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

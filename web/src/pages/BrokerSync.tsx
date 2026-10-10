import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Check, Lock, Plus, RefreshCw, X } from 'lucide-react'
import {
  fetchBrokerSessions,
  syncBroker,
  fetchBrokerCatalog,
  addBrokerConnection,
  deleteBrokerConnection,
} from '../utils/api'
import type { BrokerCatalogItem, BrokerSessionInfo } from '../types'
import { usePortfolio } from '../context/PortfolioContext'
import { BrokerCredentialsModal } from '../components/brokers/BrokerCredentialsModal'
import { brokerCode, brokerColor } from '../components/holdings/holdingsModel'
import { brokerLabel } from '../utils/portfolioFilters'
import { useMoney } from '../utils/useMoney'

type Notice = { tone: 'ok' | 'bad'; text: string }

const NEEDS_LOGIN = ['AUTH_REQUIRED', 'SESSION_EXPIRED']

const keyOf = (name: string) => name.toLowerCase().replace(/[^a-z]/g, '')

const relativeTime = (iso?: string): string => {
  if (!iso) return 'Never'
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs} hr ago`
  return `${Math.floor(hrs / 24)}d ago`
}

const absoluteTime = (iso: string): string =>
  new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })

const hostOf = (url: string): string => {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

export const BrokerSync: React.FC = () => {
  const { refresh: refreshPortfolio, holdings } = usePortfolio()
  const { compact } = useMoney()
  const [sessions, setSessions] = useState<BrokerSessionInfo[]>([])
  const [catalog, setCatalog] = useState<BrokerCatalogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<Record<string, boolean>>({})
  const [notices, setNotices] = useState<Record<string, Notice | undefined>>({})

  const [connectItem, setConnectItem] = useState<BrokerCatalogItem | null>(null)
  const [labelInput, setLabelInput] = useState('')
  const [accountIdInput, setAccountIdInput] = useState('')
  const [adding, setAdding] = useState(false)

  const [credSession, setCredSession] = useState<BrokerSessionInfo | null>(null)

  const [removeSession, setRemoveSession] = useState<BrokerSessionInfo | null>(null)
  const [wipeBlobs, setWipeBlobs] = useState(true)
  const [wiping, setWiping] = useState(false)

  const loadSessions = useCallback(async () => {
    try {
      setSessions(await fetchBrokerSessions())
      setError(null)
    } catch (err: any) {
      setError(err?.message || 'Could not load broker connections')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadCatalog = useCallback(async () => {
    try {
      setCatalog(await fetchBrokerCatalog())
    } catch (err) {
      console.error('Failed to load broker catalog:', err)
    }
  }, [])

  useEffect(() => {
    loadSessions()
    loadCatalog()
    const onMessage = (event: MessageEvent) => {
      if (event.data === 'indmoney_authorized') loadSessions()
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [loadSessions, loadCatalog])

  // "Sync all" lives in the top bar; when it finishes the portfolio reloads, so reload the cards too.
  const firstHoldingsRender = useRef(true)
  useEffect(() => {
    if (firstHoldingsRender.current) {
      firstHoldingsRender.current = false
      return
    }
    loadSessions()
  }, [holdings, loadSessions])

  const flash = (id: string, notice: Notice, ms = 5000) => {
    setNotices((p) => ({ ...p, [id]: notice }))
    setTimeout(() => setNotices((p) => ({ ...p, [id]: undefined })), ms)
  }

  const catalogFor = (s: BrokerSessionInfo) => catalog.find((c) => keyOf(c.broker_name) === keyOf(s.broker_name))
  const usesCredentials = (s: BrokerSessionInfo) => (catalogFor(s)?.credential_fields.length ?? 0) > 0
  const needsLogin = (s: BrokerSessionInfo) => NEEDS_LOGIN.includes(s.status)
  const shortName = (s: BrokerSessionInfo) => s.display_name.split(' — ')[0]

  const syncOne = async (s: BrokerSessionInfo) => {
    const id = s.connection_id
    setBusy((p) => ({ ...p, [id]: true }))
    try {
      const updated = await syncBroker(id)
      setSessions((prev) => prev.map((x) => (x.connection_id === id ? updated : x)))
      if (updated.status === 'CONNECTED') {
        await refreshPortfolio()
        flash(id, { tone: 'ok', text: `Synced. ${updated.holdings_count} positions updated.` }, 4000)
      } else if (NEEDS_LOGIN.includes(updated.status)) {
        flash(
          id,
          { tone: 'bad', text: updated.error_message || `${shortName(updated)} needs a fresh login before it can sync.` },
          8000
        )
      }
    } catch (err: any) {
      flash(id, { tone: 'bad', text: `Sync failed: ${err?.message || 'unknown error'}` }, 8000)
    } finally {
      setBusy((p) => ({ ...p, [id]: false }))
    }
  }

  const reconnect = async (s: BrokerSessionInfo) => {
    if (usesCredentials(s)) {
      setCredSession(s)
      return
    }
    if (s.auth_url) {
      window.open(s.auth_url, '_blank')
      return
    }
    const id = s.connection_id
    setBusy((p) => ({ ...p, [id]: true }))
    try {
      const fresh = await fetchBrokerSessions()
      setSessions(fresh)
      let url = fresh.find((x) => x.connection_id === id)?.auth_url
      if (!url) {
        const synced = await syncBroker(id)
        setSessions((prev) => prev.map((x) => (x.connection_id === id ? synced : x)))
        url = synced.auth_url
      }
      if (url) window.open(url, '_blank')
      else flash(id, { tone: 'bad', text: `Could not get a login link for ${shortName(s)}.` })
    } catch (err: any) {
      flash(id, { tone: 'bad', text: `Could not start login: ${err?.message || 'unknown error'}` })
    } finally {
      setBusy((p) => ({ ...p, [id]: false }))
    }
  }

  const openConnect = (item: BrokerCatalogItem) => {
    const existing = sessions.filter((s) => keyOf(s.broker_name) === keyOf(item.broker_name)).length
    setLabelInput(existing > 0 ? `Account ${existing + 1}` : '')
    setAccountIdInput('')
    setConnectItem(item)
  }

  const submitConnect = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!connectItem) return
    setAdding(true)
    try {
      const created = await addBrokerConnection({
        broker_name: connectItem.broker_name,
        account_label: labelInput.trim() || undefined,
        account_id: accountIdInput.trim() || undefined,
      })
      await Promise.all([loadSessions(), loadCatalog()])
      const item = connectItem
      setConnectItem(null)
      if (item.credential_fields.length > 0) setCredSession(created)
      else if (created.auth_url) window.open(created.auth_url, '_blank')
    } catch (err: any) {
      setError(`Could not add the connection: ${err?.message || 'unknown error'}`)
      setConnectItem(null)
    } finally {
      setAdding(false)
    }
  }

  const confirmRemove = async () => {
    if (!removeSession) return
    setWiping(true)
    try {
      const res = await deleteBrokerConnection(removeSession.connection_id, wipeBlobs)
      setRemoveSession(null)
      await Promise.all([loadSessions(), loadCatalog(), refreshPortfolio()])
      setError(null)
      console.info(`Removed connection, ${res.holdings_purged} holdings purged`)
    } catch (err: any) {
      setError(`Could not remove the connection: ${err?.message || 'unknown error'}`)
      setRemoveSession(null)
    } finally {
      setWiping(false)
    }
  }

  const stats = useMemo(() => {
    const connected = sessions.filter((s) => s.status === 'CONNECTED').length
    const lastSync = sessions.map((s) => s.last_sync_time).filter(Boolean).sort().pop()
    return {
      connected,
      attention: sessions.filter(needsLogin).length,
      value: sessions.reduce((sum, s) => sum + (s.total_valuation || 0), 0),
      positions: sessions.reduce((sum, s) => sum + (s.holdings_count || 0), 0),
      lastSync,
    }
  }, [sessions])

  if (loading && sessions.length === 0) {
    return (
      <div className="page-in" aria-busy="true">
        <p className="sub">Loading broker connections…</p>
      </div>
    )
  }

  const attention = sessions.filter(needsLogin)

  return (
    <div className="page-in">
      {error && (
        <div className="banner bad" role="alert">
          <AlertTriangle className="ic" size={18} strokeWidth={1.75} />
          <div className="tx">{error}</div>
          <button className="btn btn-ghost btn-sm" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {attention.map((s) => (
        <div className="banner" role="status" key={s.connection_id}>
          <AlertTriangle className="ic" size={18} strokeWidth={1.75} />
          <div className="tx">
            <b>{shortName(s)} {s.status === 'SESSION_EXPIRED' ? 'session expired.' : 'needs a login.'}</b>{' '}
            {s.holdings_count > 0
              ? `Its ${s.holdings_count} holdings are shown from the last successful sync${s.last_sync_time ? ` (${absoluteTime(s.last_sync_time)})` : ''} and may be stale. `
              : ''}
            {s.error_message || (usesCredentials(s) ? 'Check your API credentials and try again.' : 'Log in again to resume syncing.')}
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => reconnect(s)}>
            Reconnect {shortName(s)}
          </button>
        </div>
      ))}

      <section className="bsum" aria-label="Connection summary">
        <div className="card">
          <div className="lbl">Connected</div>
          <div className="val num">
            {stats.connected} / {sessions.length}
          </div>
          <div className="foot">{stats.attention > 0 ? `${stats.attention} needs attention` : sessions.length ? 'All healthy' : 'No brokers yet'}</div>
        </div>
        <div className="card">
          <div className="lbl">Value synced</div>
          <div className="val num">{compact(stats.value)}</div>
          <div className="foot">Holdings across all brokers</div>
        </div>
        <div className="card">
          <div className="lbl">Positions</div>
          <div className="val num">{stats.positions}</div>
          <div className="foot">Before merging across brokers</div>
        </div>
        <div className="card">
          <div className="lbl">Last sync</div>
          <div className="val num">{relativeTime(stats.lastSync)}</div>
          <div className="foot">{stats.lastSync ? absoluteTime(stats.lastSync) : 'Run a sync to pull holdings'}</div>
        </div>
      </section>

      <section aria-label="Connected brokers" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="pg-head">
          <div>
            <h2 className="h2">Your brokers</h2>
            <p className="sub">Read-only access. Nothing here can place orders or move money.</p>
          </div>
          <button className="btn btn-primary" onClick={() => document.getElementById('add-source')?.scrollIntoView({ behavior: 'smooth' })}>
            <Plus size={18} strokeWidth={1.75} /> Add broker
          </button>
        </div>

        {sessions.length === 0 ? (
          <div className="card">
            <p className="card-t">No brokers connected</p>
            <p className="card-s">Pick a broker below to link your first account.</p>
          </div>
        ) : (
          <div className="bgrid">
            {sessions.map((s) => {
              const key = keyOf(s.broker_name)
              const attn = needsLogin(s)
              const working = !!busy[s.connection_id]
              const notice = notices[s.connection_id]
              const connected = s.status === 'CONNECTED'
              const badge = working
                ? { cls: 'info', text: 'Syncing' }
                : connected
                ? { cls: 'ok', text: 'Connected' }
                : s.status === 'SESSION_EXPIRED'
                ? { cls: 'warn', text: 'Session expired' }
                : s.status === 'AUTH_REQUIRED'
                ? { cls: 'warn', text: 'Login needed' }
                : { cls: 'off', text: 'Disconnected' }
              const sessionText = attn
                ? s.error_message || (usesCredentials(s) ? 'API credentials needed' : 'Login required')
                : s.session_expires_at
                ? `Session valid until ${absoluteTime(s.session_expires_at)}`
                : s.auth_type
              return (
                <article key={s.connection_id} className={`card bc${attn ? ' attn' : ''}`}>
                  <div className="bc-h">
                    <span className="tile" style={{ background: brokerColor(key) }} aria-hidden="true">
                      {brokerCode(key)}
                    </span>
                    <div className="grow">
                      <div className="nm">
                        {shortName(s)} <span className="method">{usesCredentials(s) ? 'API' : 'MCP'}</span>
                        {s.account_label && <span className="method">{s.account_label}</span>}
                      </div>
                      <div className="acct mono">
                        {s.account_id ? `Client ${s.account_id} · ` : ''}
                        {hostOf(s.mcp_server_url)}
                      </div>
                    </div>
                    <span className={`badge ${badge.cls}`}>
                      <i /> {badge.text}
                    </span>
                  </div>

                  <div className="stats">
                    <div>
                      <div className="k">Value</div>
                      <div className="v num">{compact(s.total_valuation)}</div>
                    </div>
                    <div>
                      <div className="k">Holdings</div>
                      <div className="v num">{s.holdings_count}</div>
                    </div>
                    <div>
                      <div className="k">Last sync</div>
                      <div className="v num">{relativeTime(s.last_sync_time)}</div>
                    </div>
                  </div>

                  <div className={`sess${attn ? ' warn' : ''}`}>
                    <Lock size={16} strokeWidth={1.75} aria-hidden="true" />
                    <span>{sessionText}</span>
                  </div>

                  {notice && <div className={`note ${notice.tone}`}>{notice.text}</div>}

                  <div className="bc-f">
                    {attn && (
                      <button className="btn btn-primary btn-sm" onClick={() => reconnect(s)} disabled={working}>
                        {usesCredentials(s) ? 'Enter credentials' : 'Reconnect'}
                      </button>
                    )}
                    <button className="btn btn-sm" onClick={() => syncOne(s)} disabled={working}>
                      <RefreshCw size={16} strokeWidth={1.75} className={working ? 'spin' : ''} />
                      {working ? 'Syncing…' : 'Sync now'}
                    </button>
                    {usesCredentials(s) && !attn && (
                      <button className="btn btn-ghost btn-sm" onClick={() => setCredSession(s)}>
                        Credentials
                      </button>
                    )}
                    <span className="spacer" />
                    <button className="btn btn-danger btn-sm" onClick={() => setRemoveSession(s)}>
                      Disconnect
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>

      <section id="add-source" aria-label="Add a broker" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <h2 className="h2">Add another source</h2>
          <p className="sub">Brokers the aggregator can read from. Greyed-out ones are not available yet.</p>
        </div>
        <div className="addgrid">
          {catalog.map((item) => {
            const key = keyOf(item.broker_name)
            const soon = item.coming_soon || !item.supported
            const count = sessions.filter((s) => keyOf(s.broker_name) === key).length
            return (
              <div className="addt" key={item.broker_name}>
                <span
                  className={`tile${soon ? ' plain' : ''}`}
                  style={soon ? undefined : { background: brokerColor(key) }}
                  aria-hidden="true"
                >
                  {brokerLabel(key).charAt(0).toUpperCase()}
                </span>
                <div className="grow">
                  <div className="nm">{item.display_name.split(' — ')[0]}</div>
                  <div className="m">{soon ? 'Coming soon' : item.credential_fields.length > 0 ? 'API keys' : 'MCP login'}</div>
                </div>
                {soon ? (
                  <span className="badge off">Soon</span>
                ) : (
                  <button className="btn btn-sm" onClick={() => openConnect(item)} aria-label={`Connect ${item.display_name}`}>
                    {count > 0 ? 'Add account' : 'Connect'}
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </section>

      <section className="card sec">
        <h2 className="card-t">How your data is handled</h2>
        <p className="card-s">Applies to every connection on this page</p>
        <ul>
          {[
            'Only read endpoints are called: holdings and prices. No order placement is ever requested.',
            'API secrets and session tokens are encrypted before they are stored, and are never shown again after saving.',
            'Daily-expiring sessions (Kite, Groww, SmartAPI) ask you to log in again instead of keeping a password.',
            "Disconnecting deletes that broker's stored credentials and its synced holdings.",
          ].map((t) => (
            <li key={t}>
              <Check size={16} strokeWidth={1.75} aria-hidden="true" />
              {t}
            </li>
          ))}
        </ul>
      </section>

      {connectItem && (
        <div className="scrim" onClick={() => !adding && setConnectItem(null)}>
          <form className="modal" role="dialog" aria-modal="true" aria-labelledby="add-title" onClick={(e) => e.stopPropagation()} onSubmit={submitConnect}>
            <div className="modal-h">
              <div style={{ flex: '1 1 auto' }}>
                <h2 className="h2" id="add-title">
                  Connect {connectItem.display_name.split(' — ')[0]}
                </h2>
                <p className="sub">{connectItem.description}</p>
              </div>
              <button type="button" className="btn btn-icon btn-ghost" aria-label="Close" onClick={() => setConnectItem(null)}>
                <X size={18} strokeWidth={1.75} />
              </button>
            </div>
            <div className="modal-b">
              <div className="field">
                <label htmlFor="acct-label">Account label</label>
                <input
                  id="acct-label"
                  className="input"
                  value={labelInput}
                  onChange={(e) => setLabelInput(e.target.value)}
                  placeholder="e.g. Personal, Family HUF"
                />
                <p className="hint">Tells this account apart from other {connectItem.display_name.split(' — ')[0]} accounts.</p>
              </div>
              <div className="field">
                <label htmlFor="acct-id">
                  Client ID <em>optional</em>
                </label>
                <input
                  id="acct-id"
                  className="input mono"
                  value={accountIdInput}
                  onChange={(e) => setAccountIdInput(e.target.value)}
                  placeholder="Shown on the card for reference"
                />
              </div>
            </div>
            <div className="modal-f">
              <button type="button" className="btn" onClick={() => setConnectItem(null)} disabled={adding}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={adding}>
                {adding ? 'Connecting…' : 'Continue'}
              </button>
            </div>
          </form>
        </div>
      )}

      {removeSession && (
        <div className="scrim" onClick={() => !wiping && setRemoveSession(null)}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="rm-title" onClick={(e) => e.stopPropagation()}>
            <div className="modal-h">
              <div style={{ flex: '1 1 auto' }}>
                <h2 className="h2" id="rm-title">
                  Disconnect {shortName(removeSession)}?
                </h2>
                <p className="sub">This removes the connection and its synced data from your vault.</p>
              </div>
              <button type="button" className="btn btn-icon btn-ghost" aria-label="Close" onClick={() => setRemoveSession(null)} disabled={wiping}>
                <X size={18} strokeWidth={1.75} />
              </button>
            </div>
            <div className="modal-b">
              <div>
                {removeSession.account_label && (
                  <div className="kv">
                    <span>Account</span>
                    <span>{removeSession.account_label}</span>
                  </div>
                )}
                <div className="kv">
                  <span>Holdings removed</span>
                  <span className="num">{removeSession.holdings_count}</span>
                </div>
                <div className="kv">
                  <span>Value removed from net worth</span>
                  <span className="num">{compact(removeSession.total_valuation)}</span>
                </div>
              </div>
              <label className="check">
                <input type="checkbox" checked={wipeBlobs} onChange={(e) => setWipeBlobs(e.target.checked)} />
                <span>
                  <b>Also delete archived raw broker responses</b>
                  <br />
                  <span className="hint">The JSON snapshots kept in storage for this connection.</span>
                </span>
              </label>
            </div>
            <div className="modal-f">
              <button className="btn" onClick={() => setRemoveSession(null)} disabled={wiping}>
                Cancel
              </button>
              <button className="btn btn-primary" style={{ background: 'var(--loss)', borderColor: 'var(--loss)' }} onClick={confirmRemove} disabled={wiping}>
                {wiping ? 'Disconnecting…' : 'Disconnect'}
              </button>
            </div>
          </div>
        </div>
      )}

      {credSession && catalogFor(credSession) && (
        <BrokerCredentialsModal
          broker={catalogFor(credSession)!}
          connectionId={credSession.connection_id}
          displayName={credSession.display_name}
          alreadySaved={!!credSession.credentials_saved}
          onClose={() => setCredSession(null)}
          onVerified={async () => {
            const target = credSession
            setCredSession(null)
            await loadSessions()
            if (target) await syncOne(target)
          }}
        />
      )}
    </div>
  )
}

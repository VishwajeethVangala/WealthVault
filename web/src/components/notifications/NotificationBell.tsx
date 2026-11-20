import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  AlertTriangle,
  Bell,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react'
import { fetchNotificationsFeed } from '../../utils/api'
import type { NotificationCardItem } from '../../types'

const READ_KEY = 'wv_notifications_read_v1'

const getReadIds = (): Set<string> => {
  try {
    const raw = localStorage.getItem(READ_KEY)
    return raw ? new Set(JSON.parse(raw)) : new Set()
  } catch {
    return new Set()
  }
}

const saveReadIds = (ids: Set<string>) => {
  try {
    localStorage.setItem(READ_KEY, JSON.stringify(Array.from(ids)))
  } catch {
    // ignore
  }
}

export const NotificationBell: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false)
  const [items, setItems] = useState<NotificationCardItem[]>([])
  const [loading, setLoading] = useState(false)
  const [readIds, setReadIds] = useState<Set<string>>(getReadIds)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const loadFeed = useCallback(async () => {
    try {
      setLoading(true)
      const res = await fetchNotificationsFeed()
      setItems(res.items || [])
    } catch (err) {
      console.warn('Could not load notification feed:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadFeed()
    // Poll every 60 seconds
    const interval = setInterval(loadFeed, 60000)
    return () => clearInterval(interval)
  }, [loadFeed])

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  // Close on escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown)
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  const unreadCount = items.filter((it) => !readIds.has(it.id)).length

  const markAllRead = () => {
    const next = new Set(readIds)
    items.forEach((it) => next.add(it.id))
    setReadIds(next)
    saveReadIds(next)
  }

  const markSingleRead = (id: string) => {
    if (readIds.has(id)) return
    const next = new Set(readIds)
    next.add(id)
    setReadIds(next)
    saveReadIds(next)
  }

  const renderIcon = (item: NotificationCardItem) => {
    if (item.severity === 'danger') {
      return <TrendingDown size={18} className="text-red-500 shrink-0" />
    }
    if (item.severity === 'warning') {
      return <AlertTriangle size={18} className="text-amber-500 shrink-0" />
    }
    if (item.severity === 'success') {
      return <TrendingUp size={18} className="text-emerald-500 shrink-0" />
    }
    return <AlertCircle size={18} className="text-blue-500 shrink-0" />
  }

  const severityBadgeClass = (severity: string) => {
    if (severity === 'danger') return 'badge bad'
    if (severity === 'warning') return 'badge warn'
    if (severity === 'success') return 'badge ok'
    return 'badge info'
  }

  return (
    <div className="relative inline-block" ref={dropdownRef}>
      {/* Topbar Bell Icon Button */}
      <button
        type="button"
        className="btn btn-ghost btn-icon relative"
        onClick={() => {
          setIsOpen((prev) => !prev)
          if (!isOpen && items.length === 0) {
            void loadFeed()
          }
        }}
        aria-label="Notifications & Strategy Alerts"
        title="Notifications & Strategy Alerts"
        aria-expanded={isOpen}
      >
        <Bell size={18} strokeWidth={1.75} />
        {unreadCount > 0 && (
          <span
            className="absolute -top-1 -right-1 flex h-4 min-w-[16px] px-1 items-center justify-center rounded-full text-[10px] font-bold"
            style={{
              backgroundColor: 'var(--loss, #ef4444)',
              color: '#ffffff',
              boxShadow: '0 0 0 2px var(--surface)',
            }}
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Floating Popover Dropdown Card */}
      {isOpen && (
        <div
          className="absolute right-0 mt-2 z-50 flex flex-col rounded-xl overflow-hidden shadow-2xl border"
          style={{
            width: '400px',
            maxWidth: 'calc(100vw - 24px)',
            backgroundColor: 'var(--surface)',
            borderColor: 'var(--border)',
            boxShadow: '0 12px 36px rgba(0, 0, 0, 0.25)',
          }}
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-4 py-3 border-b"
            style={{
              backgroundColor: 'var(--surface-2)',
              borderColor: 'var(--border)',
            }}
          >
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm" style={{ color: 'var(--text)' }}>
                Strategy Alerts &amp; Calls
              </span>
              {items.length > 0 && (
                <span className="badge off num text-xs">
                  {items.length}
                </span>
              )}
            </div>

            <div className="flex items-center gap-1.5">
              <button
                type="button"
                className="btn btn-ghost btn-icon"
                style={{ width: '28px', height: '28px' }}
                onClick={loadFeed}
                title="Refresh alerts"
                disabled={loading}
              >
                <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              </button>

              {unreadCount > 0 && (
                <button
                  type="button"
                  className="text-xs font-medium px-2 py-1 rounded transition hover:opacity-80"
                  style={{
                    color: 'var(--accent)',
                    backgroundColor: 'transparent',
                  }}
                  onClick={markAllRead}
                  title="Mark all as read"
                >
                  Mark read
                </button>
              )}

              <button
                type="button"
                className="btn btn-ghost btn-icon"
                style={{ width: '28px', height: '28px' }}
                onClick={() => setIsOpen(false)}
                title="Close"
              >
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Body Cards List */}
          <div
            className="flex flex-col divide-y overflow-y-auto max-h-[460px]"
            style={{ borderColor: 'var(--border)' }}
          >
            {items.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 px-6 text-center">
                <CheckCircle2 size={36} className="text-emerald-500 mb-2 opacity-80" />
                <p className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
                  All Holdings Safe &amp; Tracking
                </p>
                <p className="text-xs mt-1 max-w-xs" style={{ color: 'var(--text-3)' }}>
                  No active exit warnings or Supertrend breakdowns right now. We will notify you the moment any held stock breaks support.
                </p>
              </div>
            ) : (
              items.map((item) => {
                const isUnread = !readIds.has(item.id)
                const isDanger = item.severity === 'danger'
                const isWarn = item.severity === 'warning'
                const isSuccess = item.severity === 'success'

                let cardBg = 'transparent'
                if (isUnread) {
                  if (isDanger) cardBg = 'rgba(239, 68, 68, 0.06)'
                  else if (isWarn) cardBg = 'rgba(245, 158, 11, 0.06)'
                  else if (isSuccess) cardBg = 'rgba(16, 185, 129, 0.06)'
                  else cardBg = 'var(--accent-weak)'
                }

                return (
                  <Link
                    key={item.id}
                    to={item.url}
                    onClick={() => {
                      markSingleRead(item.id)
                      setIsOpen(false)
                    }}
                    className="flex flex-col gap-1.5 p-3.5 transition-colors hover:brightness-95 block no-underline text-left group"
                    style={{
                      backgroundColor: cardBg,
                      borderLeft: isDanger
                        ? '3px solid var(--loss, #ef4444)'
                        : isWarn
                        ? '3px solid var(--warn, #f59e0b)'
                        : isSuccess
                        ? '3px solid var(--gain, #10b981)'
                        : '3px solid var(--accent, #3346d3)',
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        {renderIcon(item)}
                        <span className="font-bold text-xs truncate" style={{ color: 'var(--text)' }}>
                          {item.title}
                        </span>
                        {isUnread && (
                          <span
                            className="inline-block w-2 h-2 rounded-full shrink-0"
                            style={{ backgroundColor: isDanger ? 'var(--loss)' : 'var(--accent)' }}
                          />
                        )}
                      </div>
                      <span className={severityBadgeClass(item.severity)}>
                        {item.strategy}
                      </span>
                    </div>

                    <p className="text-xs font-semibold m-0" style={{ color: 'var(--text-2)' }}>
                      {item.subtitle}
                    </p>

                    <p className="text-xs m-0 line-clamp-2" style={{ color: 'var(--text-3)' }}>
                      {item.detail}
                    </p>

                    <div className="flex items-center justify-between mt-1 text-[11px]" style={{ color: 'var(--text-3)' }}>
                      <span className="num">{item.timestamp}</span>
                      <span className="flex items-center gap-0.5 text-xs font-medium group-hover:underline" style={{ color: 'var(--accent)' }}>
                        Inspect chart <ChevronRight size={12} />
                      </span>
                    </div>
                  </Link>
                )
              })
            )}
          </div>

          {/* Footer */}
          {items.length > 0 && (
            <div
              className="flex items-center justify-between px-4 py-2 text-xs border-t"
              style={{
                backgroundColor: 'var(--surface-2)',
                borderColor: 'var(--border)',
                color: 'var(--text-3)',
              }}
            >
              <span>Automated real-time strategy exit monitor</span>
              <Link
                to="/strategy?tab=supertrend"
                onClick={() => setIsOpen(false)}
                className="hover:underline flex items-center gap-1 font-medium"
                style={{ color: 'var(--accent)' }}
              >
                Strategies <ExternalLink size={11} />
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

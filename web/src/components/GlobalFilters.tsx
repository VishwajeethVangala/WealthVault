import React, { useState, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronDown, RotateCcw, Check, SlidersHorizontal, X } from 'lucide-react'

// Real custodians based on live connected broker feeds
const BROKER_OPTIONS = [
  { value: 'all', label: 'All Custodians (Zerodha + INDmoney)' },
  { value: 'zerodha', label: 'Zerodha (Kite & Coin)' },
  { value: 'indmoney', label: 'INDmoney (Equities, US & NPS)' },
]

const ASSET_CLASS_OPTIONS = [
  { value: 'all', label: 'All Asset Classes' },
  { value: 'EQUITY', label: 'Equities & ETFs' },
  { value: 'MUTUAL_FUND', label: 'Mutual Funds' },
  { value: 'GOLD', label: 'Sovereign Gold (SGB)' },
  { value: 'NPS', label: 'NPS Retirement' },
]

const RANGE_OPTIONS = [
  { value: '200D', label: '200D (Benchmark)' },
  { value: '30D', label: '30D (Monthly)' },
  { value: '90D', label: '90D (Quarterly)' },
  { value: '1Y', label: '1 Year' },
  { value: 'MAX', label: 'All-Time (MAX)' },
]

interface DropdownPillProps {
  labelPrefix: string
  currentValue: string
  options: { value: string; label: string }[]
  onChange: (val: string) => void
  isOpen: boolean
  onToggle: () => void
  onClose: () => void
}

const DropdownPill: React.FC<DropdownPillProps> = ({
  labelPrefix,
  currentValue,
  options,
  onChange,
  isOpen,
  onToggle,
  onClose,
}) => {
  const dropdownRef = useRef<HTMLDivElement>(null)
  const selectedOption = options.find((opt) => opt.value === currentValue) || options[0]
  const isFiltered = currentValue !== 'all' && currentValue !== '200D'

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        onClose()
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen, onClose])

  return (
    <div className="relative inline-block" ref={dropdownRef}>
      <button
        type="button"
        onClick={onToggle}
        className={`h-8 inline-flex items-center gap-2 px-3 rounded-lg text-xs font-medium transition-all select-none border ${
          isFiltered
            ? 'bg-primary-container text-on-primary border-primary shadow-sm'
            : 'bg-surface-container-lowest text-on-surface hover:bg-surface-container-low border-outline-variant/40 shadow-[0_1px_3px_rgba(0,0,0,0.02)]'
        }`}
      >
        <span
          className={`text-[10px] font-semibold uppercase tracking-wider ${
            isFiltered ? 'text-on-primary/70' : 'text-outline'
          }`}
        >
          {labelPrefix}:
        </span>
        <span className="font-semibold truncate max-w-[170px]">{selectedOption.label}</span>
        <ChevronDown
          className={`w-3.5 h-3.5 transition-transform duration-150 ${
            isFiltered ? 'text-on-primary' : 'text-outline'
          } ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <div className="absolute left-0 mt-1.5 w-60 bg-surface-container-lowest rounded-xl shadow-xl border border-outline-variant/30 p-1.5 z-50 flex flex-col gap-0.5 animate-in fade-in zoom-in-95 duration-100">
          <div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-outline border-b border-surface-container mb-1">
            Select {labelPrefix}
          </div>
          {options.map((opt) => {
            const isSelected = opt.value === currentValue
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  onChange(opt.value)
                  onClose()
                }}
                className={`w-full text-left px-3 py-2 rounded-lg text-xs flex items-center justify-between transition-colors ${
                  isSelected
                    ? 'bg-primary text-on-primary font-semibold'
                    : 'text-on-surface hover:bg-surface-container-low font-medium'
                }`}
              >
                <span className="truncate pr-2">{opt.label}</span>
                {isSelected && <Check className="w-3.5 h-3.5 text-on-primary shrink-0" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export const GlobalFilters: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const [openDropdown, setOpenDropdown] = useState<string | null>(null)

  const currentBroker = searchParams.get('broker') || 'all'
  const currentAssetClass = searchParams.get('assetClass') || 'all'
  const currentRange = searchParams.get('range') || '200D'

  const updateParam = (key: string, value: string) => {
    const nextParams = new URLSearchParams(searchParams)
    if (value === 'all' && key !== 'range') {
      nextParams.delete(key)
    } else if (key === 'range' && value === '200D') {
      nextParams.delete('range')
    } else {
      nextParams.set(key, value)
    }
    setSearchParams(nextParams, { replace: true })
  }

  const handleReset = () => {
    setSearchParams(new URLSearchParams(), { replace: true })
    setOpenDropdown(null)
  }

  const hasActiveFilters =
    currentBroker !== 'all' ||
    currentAssetClass !== 'all' ||
    currentRange !== '200D'

  return (
    <div className="h-12 w-full bg-surface-container-low/80 border-t border-surface-container backdrop-blur-md">
      <div className="h-full max-w-[1440px] mx-auto px-gutter-desktop flex items-center justify-between gap-4">
        {/* Left: Looker Studio Filter Dropdowns */}
        <div className="flex items-center gap-2.5 overflow-visible py-1">
          <div className="hidden lg:flex items-center gap-1.5 text-outline text-xs font-semibold mr-1">
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span className="text-[11px] uppercase tracking-wider">Filters</span>
          </div>

          <DropdownPill
            labelPrefix="Custodian"
            currentValue={currentBroker}
            options={BROKER_OPTIONS}
            onChange={(val) => updateParam('broker', val)}
            isOpen={openDropdown === 'broker'}
            onToggle={() => setOpenDropdown(openDropdown === 'broker' ? null : 'broker')}
            onClose={() => setOpenDropdown(null)}
          />

          <DropdownPill
            labelPrefix="Asset Class"
            currentValue={currentAssetClass}
            options={ASSET_CLASS_OPTIONS}
            onChange={(val) => updateParam('assetClass', val)}
            isOpen={openDropdown === 'assetClass'}
            onToggle={() => setOpenDropdown(openDropdown === 'assetClass' ? null : 'assetClass')}
            onClose={() => setOpenDropdown(null)}
          />

          <DropdownPill
            labelPrefix="Horizon"
            currentValue={currentRange}
            options={RANGE_OPTIONS}
            onChange={(val) => updateParam('range', val)}
            isOpen={openDropdown === 'range'}
            onToggle={() => setOpenDropdown(openDropdown === 'range' ? null : 'range')}
            onClose={() => setOpenDropdown(null)}
          />

          {hasActiveFilters && (
            <button
              type="button"
              onClick={handleReset}
              className="h-8 inline-flex items-center gap-1.5 px-3 bg-surface-container-lowest hover:bg-error-container/20 rounded-lg shadow-sm border border-error/20 text-error text-xs font-semibold transition-all ml-1 group"
              title="Reset all filters to defaults"
            >
              <RotateCcw className="w-3 h-3 group-hover:-rotate-90 transition-transform" />
              <span>Reset</span>
            </button>
          )}
        </div>

        {/* Right: Active Filter Badges & Status */}
        <div className="flex items-center gap-3 shrink-0">
          {hasActiveFilters ? (
            <div className="hidden sm:flex items-center gap-1.5">
              {currentBroker !== 'all' && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-container text-on-surface text-[11px] font-medium">
                  {currentBroker === 'zerodha' ? 'Zerodha' : 'INDmoney'}
                  <button
                    onClick={() => updateParam('broker', 'all')}
                    className="hover:text-error"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}
              {currentAssetClass !== 'all' && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-container text-on-surface text-[11px] font-medium">
                  {currentAssetClass.replace('_', ' ')}
                  <button
                    onClick={() => updateParam('assetClass', 'all')}
                    className="hover:text-error"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              )}
            </div>
          ) : (
            <div className="hidden sm:flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-on-tertiary-container opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-on-tertiary-container"></span>
              </span>
              <span className="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider">
                Audited Live Feed
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

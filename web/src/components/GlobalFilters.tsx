import React, { useState, useRef, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  ChevronDown,
  RotateCcw,
  Check,
  SlidersHorizontal,
  X,
  Search,
  Layers,
  Building2,
} from 'lucide-react'
import { usePortfolio } from '../context/PortfolioContext'
import { brokerLabel } from '../utils/portfolioFilters'

interface FilterOption {
  value: string
  label: string
  count?: number
  colorDot?: string
  icon?: React.ComponentType<{ className?: string }>
}

interface MultiSelectDropdownPillProps {
  labelPrefix: string
  icon: React.ComponentType<{ className?: string }>
  selectedValues: string[] // Array of selected option values, e.g. ['EQUITY', 'MUTUAL_FUND'] or empty for 'all'
  options: FilterOption[]
  onChange: (values: string[]) => void
  isOpen: boolean
  onToggle: () => void
  onClose: () => void
  searchable?: boolean
}

export const MultiSelectDropdownPill: React.FC<MultiSelectDropdownPillProps> = ({
  labelPrefix,
  icon: Icon,
  selectedValues,
  options,
  onChange,
  isOpen,
  onToggle,
  onClose,
  searchable = false,
}) => {
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [searchTerm, setSearchTerm] = useState('')

  // All selectable values (excluding 'all')
  const actualOptions = useMemo(() => options.filter((o) => o.value !== 'all'), [options])
  const allValues = useMemo(() => actualOptions.map((o) => o.value), [actualOptions])

  // Is "all" currently effective? (either empty array or contains all items)
  const isAllSelected = selectedValues.length === 0 || selectedValues.length === allValues.length
  const isFiltered = !isAllSelected && selectedValues.length > 0

  // Outside click listener
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        onClose()
      }
    }
    if (isOpen) {
      const timer = setTimeout(() => {
        document.addEventListener('click', handleClickOutside)
      }, 0)
      if (searchable) {
        setTimeout(() => inputRef.current?.focus(), 50)
      }
      return () => {
        clearTimeout(timer)
        document.removeEventListener('click', handleClickOutside)
      }
    } else {
      setSearchTerm('')
    }
  }, [isOpen, onClose, searchable])

  // Filter options by search term
  const filteredOptions = useMemo(() => {
    if (!searchTerm.trim()) return actualOptions
    const q = searchTerm.toLowerCase().trim()
    return actualOptions.filter((opt) => opt.label.toLowerCase().includes(q))
  }, [actualOptions, searchTerm])

  // Compute display label on the pill trigger
  const displayLabel = useMemo(() => {
    if (isAllSelected) {
      return `All (${actualOptions.length})`
    }
    if (selectedValues.length === 1) {
      const opt = actualOptions.find((o) => o.value === selectedValues[0])
      return opt ? opt.label : selectedValues[0]
    }
    return `${selectedValues.length} Selected`
  }, [isAllSelected, selectedValues, actualOptions])

  // Compute total holding count for currently selected subset
  const displayCount = useMemo(() => {
    if (isAllSelected) {
      const allOpt = options.find((o) => o.value === 'all')
      return allOpt?.count
    }
    return selectedValues.reduce((sum, val) => {
      const opt = actualOptions.find((o) => o.value === val)
      return sum + (opt?.count || 0)
    }, 0)
  }, [isAllSelected, selectedValues, options, actualOptions])

  // Toggle an individual option
  const handleToggleOption = (val: string) => {
    if (isAllSelected) {
      // If all are selected, unchecking one leaves the others selected
      const next = allValues.filter((v) => v !== val)
      onChange(next)
    } else if (selectedValues.includes(val)) {
      const next = selectedValues.filter((v) => v !== val)
      onChange(next.length === 0 ? [] : next)
    } else {
      const next = [...selectedValues, val]
      onChange(next.length === allValues.length ? [] : next)
    }
  }

  // "Select All" toggle
  const handleToggleAll = () => {
    onChange([])
  }

  // Looker Studio "Only" shortcut
  const handleSelectOnly = (val: string, e: React.MouseEvent) => {
    e.stopPropagation()
    onChange([val])
  }

  return (
    <div className="relative inline-block" ref={dropdownRef}>
      <button
        type="button"
        onClick={onToggle}
        className={`h-8 inline-flex items-center gap-2 px-3 rounded-xl text-xs font-semibold transition-all duration-150 select-none border shrink-0 ${
          isFiltered
            ? 'bg-wv-text text-wv-bg border-wv-text shadow-sm'
            : 'bg-wv-surface text-wv-text-2 hover:text-wv-text hover:bg-wv-surface-2 border-wv-border shadow-[0_1px_2px_rgba(0,0,0,0.03)]'
        }`}
      >
        <Icon className={`w-3.5 h-3.5 ${isFiltered ? 'text-wv-gain' : 'text-wv-text-3'}`} />
        <span
          className={`text-[10px] font-bold uppercase tracking-wider ${
            isFiltered ? 'text-wv-text-3' : 'text-wv-text-3'
          }`}
        >
          {labelPrefix}:
        </span>
        <span className="whitespace-nowrap font-semibold">{displayLabel}</span>
        {displayCount !== undefined && (
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-mono leading-tight ${
              isFiltered ? 'bg-wv-surface text-wv-text font-bold' : 'bg-wv-surface-2 text-wv-text-3'
            }`}
          >
            {displayCount}
          </span>
        )}
        <ChevronDown
          className={`w-3.5 h-3.5 transition-transform duration-150 ${
            isFiltered ? 'text-wv-text-3' : 'text-wv-text-3'
          } ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <div className="absolute left-0 mt-2 w-72 bg-wv-surface rounded-2xl shadow-xl border border-wv-border p-2 z-50 flex flex-col gap-1 animate-in fade-in zoom-in-95 duration-100">
          {/* Header */}
          <div className="px-2.5 py-1.5 flex items-center justify-between border-b border-wv-border mb-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-wv-text-3">
              Filter by {labelPrefix}
            </span>
            {isFiltered && (
              <button
                type="button"
                onClick={() => onChange([])}
                className="text-[10px] font-semibold text-wv-loss hover:text-wv-loss flex items-center gap-1 transition-colors"
              >
                <span>Reset to All</span>
              </button>
            )}
          </div>

          {/* Optional Search Bar */}
          {searchable && actualOptions.length > 4 && (
            <div className="relative px-1 mb-1">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-wv-text-3 pointer-events-none" />
              <input
                ref={inputRef}
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder={`Search ${labelPrefix.toLowerCase()}...`}
                className="w-full h-8 pl-8 pr-7 text-xs bg-wv-surface-2 rounded-xl border border-wv-border focus:outline-none focus:border-wv-text focus:bg-wv-surface transition-all text-wv-text placeholder:text-wv-text-3 font-medium"
              />
              {searchTerm && (
                <button
                  type="button"
                  onClick={() => setSearchTerm('')}
                  className="absolute right-3 top-2.5 text-wv-text-3 hover:text-wv-text-2"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )}

          {/* "Select All" Option */}
          {!searchTerm && (
            <div
              className={`group flex items-center justify-between px-2.5 py-2 rounded-xl text-xs transition-colors cursor-pointer border-b border-wv-border mb-0.5 ${
                isAllSelected
                  ? 'bg-wv-surface-2 text-wv-text font-bold'
                  : 'text-wv-text-2 hover:bg-wv-surface-2 font-medium'
              }`}
              onClick={handleToggleAll}
            >
              <div className="flex items-center gap-2.5 min-w-0 pr-2">
                <div
                  className={`w-4 h-4 rounded-md flex items-center justify-center transition-colors border ${
                    isAllSelected
                      ? 'bg-wv-text border-wv-text text-wv-bg'
                      : 'border-wv-border-strong bg-wv-surface group-hover:border-wv-border-strong'
                  }`}
                >
                  {isAllSelected && <Check className="w-3 h-3 text-wv-gain stroke-[3]" />}
                </div>
                <span className="font-semibold">Select All</span>
              </div>
              <span className="font-mono text-[10px] text-wv-text-3">
                {actualOptions.length} items
              </span>
            </div>
          )}

          {/* Options List with Checkboxes */}
          <div className="max-h-60 overflow-y-auto flex flex-col gap-0.5 pr-0.5">
            {filteredOptions.map((opt) => {
              const isChecked = isAllSelected || selectedValues.includes(opt.value)
              return (
                <div
                  key={opt.value}
                  className={`group flex items-center justify-between px-2.5 py-2 rounded-xl text-xs transition-colors cursor-pointer ${
                    isChecked && !isAllSelected
                      ? 'bg-wv-surface-2 text-wv-text font-semibold'
                      : 'text-wv-text-2 hover:bg-wv-surface-2 font-medium'
                  }`}
                  onClick={() => handleToggleOption(opt.value)}
                >
                  <div className="flex items-center gap-2.5 min-w-0 pr-2">
                    <div
                      className={`w-4 h-4 rounded-md flex items-center justify-center transition-colors border shrink-0 ${
                        isChecked
                          ? 'bg-wv-text border-wv-text text-wv-bg'
                          : 'border-wv-border-strong bg-wv-surface group-hover:border-wv-border-strong'
                      }`}
                    >
                      {isChecked && <Check className="w-3 h-3 text-wv-gain stroke-[3]" />}
                    </div>

                    {opt.colorDot && (
                      <span className={`w-2 h-2 rounded-full shrink-0 ${opt.colorDot}`} />
                    )}
                    <span className="truncate">{opt.label}</span>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {opt.count !== undefined && (
                      <span
                        className={`font-mono text-[10px] px-1.5 py-0.5 rounded-md ${
                          isChecked && !isAllSelected
                            ? 'bg-wv-border text-wv-text font-bold'
                            : 'bg-wv-surface-2 text-wv-text-3'
                        }`}
                      >
                        {opt.count}
                      </span>
                    )}
                    {/* Looker Studio 'ONLY' hover shortcut */}
                    {(!isChecked || selectedValues.length > 1 || isAllSelected) && (
                      <button
                        type="button"
                        onClick={(e) => handleSelectOnly(opt.value, e)}
                        className="opacity-0 group-hover:opacity-100 text-[10px] font-bold uppercase tracking-wider text-wv-text-3 hover:text-wv-text transition-opacity px-1"
                        title={`Select only ${opt.label}`}
                      >
                        Only
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
            {filteredOptions.length === 0 && (
              <div className="py-4 text-center text-xs text-wv-text-3">
                No matches found
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export const GlobalFilters: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const { counts } = usePortfolio()
  const [openDropdown, setOpenDropdown] = useState<string | null>(null)
  const [isMobileDrawerOpen, setIsMobileDrawerOpen] = useState(false)

  // Current selections parsed as string arrays (empty array signifies 'all')
  const brokerParam = searchParams.get('broker') || 'all'
  const assetClassParam = searchParams.get('assetClass') || 'all'

  const selectedBrokers = useMemo(() => {
    return brokerParam !== 'all' ? brokerParam.split(',').filter(Boolean) : []
  }, [brokerParam])

  const selectedAssetClasses = useMemo(() => {
    return assetClassParam !== 'all' ? assetClassParam.split(',').filter(Boolean) : []
  }, [assetClassParam])

  // Update multi-select URL params
  const updateBrokers = (values: string[]) => {
    const nextParams = new URLSearchParams(searchParams)
    const allCount = brokerOptions.filter((o) => o.value !== 'all').length
    if (values.length === 0 || values.length === allCount) {
      nextParams.delete('broker')
    } else {
      nextParams.set('broker', values.join(','))
    }
    setSearchParams(nextParams, { replace: true })
  }

  const updateAssetClasses = (values: string[]) => {
    const nextParams = new URLSearchParams(searchParams)
    const allCount = assetClassOptions.filter((o) => o.value !== 'all').length
    if (values.length === 0 || values.length === allCount) {
      nextParams.delete('assetClass')
    } else {
      nextParams.set('assetClass', values.join(','))
    }
    setSearchParams(nextParams, { replace: true })
  }

  // Remove a single value from multi-select
  const removeBrokerValue = (val: string) => {
    const remaining = selectedBrokers.filter((b) => b !== val)
    updateBrokers(remaining)
  }

  const removeAssetClassValue = (val: string) => {
    const remaining = selectedAssetClasses.filter((a) => a !== val)
    updateAssetClasses(remaining)
  }

  const handleReset = () => {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete('broker')
    nextParams.delete('assetClass')
    setSearchParams(nextParams, { replace: true })
    setOpenDropdown(null)
    setIsMobileDrawerOpen(false)
  }

  const isBrokerFiltered = selectedBrokers.length > 0
  const isAssetFiltered = selectedAssetClasses.length > 0
  const hasActiveFilters = isBrokerFiltered || isAssetFiltered

  const activeFilterCount =
    (isBrokerFiltered ? selectedBrokers.length : 0) +
    (isAssetFiltered ? selectedAssetClasses.length : 0)

  // 1. Custodian Options with live counts
  const brokerOptions: FilterOption[] = [
    { value: 'all', label: 'All Custodians', count: counts.total },
    ...Object.entries(counts.byBroker).map(([key, count]) => ({ value: key, label: brokerLabel(key), count })),
  ]

  // 2. Asset Class Options with live counts & canonical theme dots
  const assetClassOptions: FilterOption[] = [
    { value: 'all', label: 'All Asset Classes', count: counts.total },
    {
      value: 'EQUITY',
      label: 'Indian Equities & ETFs',
      count: counts.byAssetClass.EQUITY,
      colorDot: 'bg-wv-text',
    },
    {
      value: 'MUTUAL_FUND',
      label: 'Mutual Funds',
      count: counts.byAssetClass.MUTUAL_FUND,
      colorDot: 'bg-cyan-600',
    },
    {
      value: 'US_STOCKS',
      label: 'US Equities & Tech',
      count: counts.byAssetClass.US_STOCKS,
      colorDot: 'bg-wv-accent',
    },
    {
      value: 'GOLD',
      label: 'Sovereign Gold (SGB)',
      count: counts.byAssetClass.GOLD,
      colorDot: 'bg-wv-warn',
    },
    {
      value: 'NPS',
      label: 'NPS Retirement',
      count: counts.byAssetClass.NPS,
      colorDot: 'bg-wv-accent',
    },
  ]

  return (
    <div className="h-12 w-full bg-wv-surface backdrop-blur-md border-b border-wv-border shadow-[0_1px_2px_rgba(0,0,0,0.02)] select-none">
      <div className="h-full w-full px-4 sm:px-6 lg:px-8 xl:px-10 flex items-center justify-between gap-3">
        {/* Left: Looker Studio Filter Dropdown Pills */}
        <div className="flex items-center gap-2 overflow-x-auto sm:overflow-visible py-1 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
          <div className="hidden sm:flex items-center gap-1.5 text-wv-text-3 text-xs font-bold mr-1 shrink-0 uppercase tracking-wider">
            <SlidersHorizontal className="w-3.5 h-3.5 text-wv-text-3" />
            <span className="text-[10px]">Controls</span>
          </div>

          <MultiSelectDropdownPill
            labelPrefix="Custodian"
            icon={Building2}
            selectedValues={selectedBrokers}
            options={brokerOptions}
            onChange={updateBrokers}
            isOpen={openDropdown === 'broker'}
            onToggle={() => setOpenDropdown(openDropdown === 'broker' ? null : 'broker')}
            onClose={() => setOpenDropdown(null)}
          />

          <MultiSelectDropdownPill
            labelPrefix="Asset Class"
            icon={Layers}
            selectedValues={selectedAssetClasses}
            options={assetClassOptions}
            onChange={updateAssetClasses}
            isOpen={openDropdown === 'assetClass'}
            onToggle={() => setOpenDropdown(openDropdown === 'assetClass' ? null : 'assetClass')}
            onClose={() => setOpenDropdown(null)}
            searchable
          />

          {hasActiveFilters && (
            <button
              type="button"
              onClick={handleReset}
              className="h-8 inline-flex items-center gap-1.5 px-3 bg-wv-surface hover:bg-wv-loss-weak text-wv-loss rounded-xl text-xs font-semibold border border-wv-loss transition-all ml-1 shrink-0 group shadow-sm"
              title="Reset all filters"
            >
              <RotateCcw className="w-3 h-3 group-hover:-rotate-90 transition-transform" />
              <span>Reset</span>
            </button>
          )}
        </div>

        {/* Right: Active Dismissible Chips & Live Metric Badge */}
        <div className="flex items-center gap-2 shrink-0">
          {hasActiveFilters ? (
            <div className="hidden md:flex items-center gap-1.5 flex-wrap">
              {selectedBrokers.map((brokerVal) => (
                <span
                  key={brokerVal}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-wv-surface-2 text-wv-text text-[11px] font-semibold border border-wv-border"
                >
                  <span>{brokerLabel(brokerVal)}</span>
                  <button
                    type="button"
                    onClick={() => removeBrokerValue(brokerVal)}
                    className="text-wv-text-3 hover:text-wv-loss transition-colors ml-0.5"
                    title={`Remove ${brokerVal}`}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}

              {selectedAssetClasses.map((acVal) => {
                const opt = assetClassOptions.find((o) => o.value === acVal)
                return (
                  <span
                    key={acVal}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-wv-surface-2 text-wv-text text-[11px] font-semibold border border-wv-border"
                  >
                    {opt?.colorDot && <span className={`w-1.5 h-1.5 rounded-full ${opt.colorDot}`} />}
                    <span>{opt?.label || acVal}</span>
                    <button
                      type="button"
                      onClick={() => removeAssetClassValue(acVal)}
                      className="text-wv-text-3 hover:text-wv-loss transition-colors ml-0.5"
                      title={`Remove ${opt?.label || acVal}`}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                )
              })}
            </div>
          ) : (
            <div className="hidden sm:flex items-center gap-2 text-wv-text-3 text-xs">
              <span className="font-mono font-bold text-wv-text">{counts.total}</span>
              <span>total audited assets</span>
            </div>
          )}

          {/* Mobile Filter Sheet Trigger */}
          <button
            type="button"
            onClick={() => setIsMobileDrawerOpen(!isMobileDrawerOpen)}
            className={`sm:hidden h-8 px-2.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 border transition-all ${
              hasActiveFilters
                ? 'bg-wv-text text-wv-bg border-wv-text shadow-sm'
                : 'bg-wv-surface text-wv-text-2 border-wv-border'
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>Filters</span>
            {activeFilterCount > 0 && (
              <span className="w-4 h-4 rounded-full bg-wv-gain text-wv-text text-[10px] font-bold flex items-center justify-center font-mono">
                {activeFilterCount}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Mobile Modal / Touch Bottom Sheet with Checkbox Multi-Select */}
      {isMobileDrawerOpen && (
        <div className="fixed inset-0 z-50 sm:hidden flex flex-col justify-end bg-wv-text backdrop-blur-sm">
          <div className="bg-wv-surface rounded-t-3xl p-5 shadow-2xl border-t border-wv-border flex flex-col gap-4 max-h-[80vh] overflow-y-auto animate-in slide-in-from-bottom duration-200">
            <div className="flex items-center justify-between pb-3 border-b border-wv-border">
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="w-4 h-4 text-wv-text" />
                <span className="font-bold text-wv-text text-sm">Portfolio Controls</span>
              </div>
              <div className="flex items-center gap-2">
                {hasActiveFilters && (
                  <button
                    type="button"
                    onClick={handleReset}
                    className="text-xs font-semibold text-wv-loss px-2 py-1 hover:bg-wv-loss-weak rounded-lg transition-colors"
                  >
                    Reset All
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setIsMobileDrawerOpen(false)}
                  className="p-1 rounded-lg text-wv-text-3 hover:text-wv-text-2 hover:bg-wv-surface-2"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Mobile Dimension 1: Custodian Multi-Select */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-wv-text-3">
                  Custodian
                </span>
                <button
                  type="button"
                  onClick={() => updateBrokers([])}
                  className="text-[10px] font-semibold text-wv-text-3 hover:text-wv-text"
                >
                  {selectedBrokers.length === 0 ? 'All Selected' : 'Reset to All'}
                </button>
              </div>
              <div className="grid grid-cols-1 gap-1">
                {brokerOptions.filter((b) => b.value !== 'all').map((b) => {
                  const isChecked = selectedBrokers.length === 0 || selectedBrokers.includes(b.value)
                  return (
                    <button
                      key={b.value}
                      type="button"
                      onClick={() => {
                        if (selectedBrokers.length === 0) {
                          updateBrokers(brokerOptions.filter((o) => o.value !== 'all' && o.value !== b.value).map((o) => o.value))
                        } else if (selectedBrokers.includes(b.value)) {
                          const rem = selectedBrokers.filter((v) => v !== b.value)
                          updateBrokers(rem)
                        } else {
                          updateBrokers([...selectedBrokers, b.value])
                        }
                      }}
                      className={`h-9 px-3 rounded-xl text-xs flex items-center justify-between font-semibold border transition-all ${
                        isChecked && selectedBrokers.length > 0
                          ? 'bg-wv-text text-wv-bg border-wv-text'
                          : isChecked
                          ? 'bg-wv-surface-2 text-wv-text border-wv-border'
                          : 'bg-wv-surface-2 text-wv-text-3 border-wv-border opacity-60'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-3.5 h-3.5 rounded flex items-center justify-center border ${
                            isChecked
                              ? 'bg-wv-gain border-wv-gain text-wv-text'
                              : 'border-wv-border-strong bg-wv-surface'
                          }`}
                        >
                          {isChecked && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                        </div>
                        <span>{b.label}</span>
                      </div>
                      {b.count !== undefined && (
                        <span className="font-mono text-[10px] opacity-80">{b.count}</span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Mobile Dimension 2: Asset Class Multi-Select */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-wv-text-3">
                  Asset Class
                </span>
                <button
                  type="button"
                  onClick={() => updateAssetClasses([])}
                  className="text-[10px] font-semibold text-wv-text-3 hover:text-wv-text"
                >
                  {selectedAssetClasses.length === 0 ? 'All Selected' : 'Reset to All'}
                </button>
              </div>
              <div className="grid grid-cols-1 gap-1.5">
                {assetClassOptions.filter((a) => a.value !== 'all').map((a) => {
                  const isChecked = selectedAssetClasses.length === 0 || selectedAssetClasses.includes(a.value)
                  return (
                    <button
                      key={a.value}
                      type="button"
                      onClick={() => {
                        if (selectedAssetClasses.length === 0) {
                          updateAssetClasses(assetClassOptions.filter((o) => o.value !== 'all' && o.value !== a.value).map((o) => o.value))
                        } else if (selectedAssetClasses.includes(a.value)) {
                          const rem = selectedAssetClasses.filter((v) => v !== a.value)
                          updateAssetClasses(rem)
                        } else {
                          updateAssetClasses([...selectedAssetClasses, a.value])
                        }
                      }}
                      className={`h-9 px-2.5 rounded-xl text-xs flex items-center justify-between font-semibold border transition-all ${
                        isChecked && selectedAssetClasses.length > 0
                          ? 'bg-wv-text text-wv-bg border-wv-text'
                          : isChecked
                          ? 'bg-wv-surface-2 text-wv-text border-wv-border'
                          : 'bg-wv-surface-2 text-wv-text-3 border-wv-border opacity-60'
                      }`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <div
                          className={`w-3.5 h-3.5 rounded flex items-center justify-center border shrink-0 ${
                            isChecked
                              ? 'bg-wv-gain border-wv-gain text-wv-text'
                              : 'border-wv-border-strong bg-wv-surface'
                          }`}
                        >
                          {isChecked && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                        </div>
                        {a.colorDot && (
                          <span className={`w-2 h-2 rounded-full shrink-0 ${a.colorDot}`} />
                        )}
                        <span className="truncate">{a.label}</span>
                      </div>
                      {a.count !== undefined && (
                        <span className="font-mono text-[10px] ml-1 opacity-80">{a.count}</span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>

            <button
              type="button"
              onClick={() => setIsMobileDrawerOpen(false)}
              className="mt-2 w-full h-11 bg-wv-text text-wv-bg text-xs font-bold rounded-xl shadow-sm"
            >
              Apply &amp; View Results
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

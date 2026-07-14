'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Settings, X, Plus, Globe } from 'lucide-react'

type TimePreset = 'LAST_YEAR' | 'LAST_2_YEARS' | 'LAST_5_YEARS' | 'LAST_10_YEARS' | 'SINCE_2000' | 'ANY' | 'CUSTOM'

const TIME_PRESET_LABELS: Record<TimePreset, string> = {
  LAST_YEAR: 'Last year',
  LAST_2_YEARS: 'Last 2 years',
  LAST_5_YEARS: 'Last 5 years',
  LAST_10_YEARS: 'Last 10 years',
  SINCE_2000: 'Since 2000',
  ANY: 'Any time',
  CUSTOM: 'Custom range',
}

const SPECIAL_REGIONS = [
  'UK', 'All but UK', 'OECD members', 'Europe', 'Nordics',
  'North America', 'APAC', 'G7', 'G20',
]

const COUNTRY_LIST = [
  'USA', 'Spain', 'Japan', 'Canada', 'Germany', 'Sweden', 'Australia', 'France',
  'Brazil', 'Netherlands', 'Italy', 'Portugal', 'Mexico', 'Turkey', 'Austria',
  'Singapore', 'China', 'Switzerland', 'Belgium', 'South Africa', 'Ireland',
  'Denmark', 'New Zealand', 'India', 'South Korea', 'Norway', 'Finland',
  'Israel', 'Chile', 'Colombia', 'Poland', 'Czech Republic', 'Argentina',
]

const ANYWHERE_VALUE = 'All'

export interface FilterValues {
  sources: ('openalex' | 'overton')[]
  maxResults: number
  timePreset: TimePreset
  customFrom?: string
  customTo?: string
  geography: string[]
}

export interface FilterCardInitialValues {
  sources?: ('openalex' | 'overton')[]
  maxResults?: number
  timePreset?: TimePreset
  customFrom?: string
  customTo?: string
  geography?: string[]
}

export type FilterSection = 'sources' | 'breadth' | 'time' | 'geography'

interface FiltersCardProps {
  title?: string
  description?: string
  confirmLabel?: string
  visibleSections?: FilterSection[]
  initialValues?: FilterCardInitialValues
  onConfirm: (filters: FilterValues) => void
  disabled?: boolean
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'px-3 py-1.5 text-sm rounded-full border transition-colors',
        active
          ? 'bg-blue-100 border-blue-300 text-blue-800 font-medium'
          : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
      )}
    >
      {children}
    </button>
  )
}

export function FiltersCard({
  title = 'Recommended Search Scope',
  description = 'These defaults give you a broad first pass. Adjust them if you want a narrower or wider scan before continuing.',
  confirmLabel = 'Continue with this approach',
  visibleSections = ['sources', 'breadth', 'time', 'geography'],
  initialValues,
  onConfirm,
  disabled,
}: FiltersCardProps) {
  const [sources, setSources] = useState<('openalex' | 'overton')[]>(
    initialValues?.sources || ['openalex', 'overton']
  )
  const [maxResults, setMaxResults] = useState(initialValues?.maxResults || 25)
  const [timePreset, setTimePreset] = useState<TimePreset>(initialValues?.timePreset || 'LAST_10_YEARS')
  const [customFrom, setCustomFrom] = useState(initialValues?.customFrom || '')
  const [customTo, setCustomTo] = useState(initialValues?.customTo || '')
  const [geography, setGeography] = useState<string[]>(initialValues?.geography || [ANYWHERE_VALUE])
  const [showCountryDropdown, setShowCountryDropdown] = useState(false)

  const toggleSource = (source: 'openalex' | 'overton') => {
    setSources((prev) => {
      if (prev.includes(source)) {
        if (prev.length === 1) return prev // Must have at least one
        return prev.filter((s) => s !== source)
      }
      return [...prev, source]
    })
  }

  const addGeo = (geo: string) => {
    if (geo === ANYWHERE_VALUE) {
      setGeography([ANYWHERE_VALUE])
    } else {
      setGeography((prev) => {
        const filtered = prev.filter((g) => g !== ANYWHERE_VALUE)
        if (filtered.includes(geo)) return filtered
        return [...filtered, geo]
      })
    }
    setShowCountryDropdown(false)
  }

  const removeGeo = (geo: string) => {
    setGeography((prev) => {
      const next = prev.filter((g) => g !== geo)
      return next.length > 0 ? next : [ANYWHERE_VALUE]
    })
  }

  const handleConfirm = () => {
    onConfirm({
      sources,
      maxResults,
      timePreset,
      customFrom: timePreset === 'CUSTOM' ? customFrom : undefined,
      customTo: timePreset === 'CUSTOM' ? customTo : undefined,
      geography,
    })
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center gap-2">
        <Settings className="w-4 h-4 text-slate-500" />
        <span className="text-sm font-semibold text-slate-700">{title}</span>
      </div>

      <div className="p-4 space-y-5">
        <p className="text-sm text-slate-600">{description}</p>

        {/* Sources */}
        {visibleSections.includes('sources') && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Evidence sources</h4>
          <div className="flex flex-wrap gap-2">
            <Chip active={sources.includes('openalex')} onClick={() => toggleSource('openalex')}>
              Academic literature
            </Chip>
            <Chip active={sources.includes('overton')} onClick={() => toggleSource('overton')}>
              Grey literature (think tanks &amp; governments)
            </Chip>
          </div>
        </div>
        )}

        {visibleSections.includes('breadth') && (
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Breadth</h4>
            <div className="flex items-center gap-3 bg-slate-50 rounded-lg p-2.5 border border-slate-100">
              <span className="text-xs text-slate-600">How wide should the first pass be?</span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setMaxResults(Math.max(5, maxResults - 5))}
                  className="w-6 h-6 rounded border border-slate-300 text-sm hover:bg-slate-100 flex items-center justify-center"
                >
                  -
                </button>
                <span className="w-8 text-center text-sm font-semibold">{maxResults}</span>
                <button
                  type="button"
                  onClick={() => setMaxResults(Math.min(200, maxResults + 5))}
                  className="w-6 h-6 rounded border border-slate-300 text-sm hover:bg-slate-100 flex items-center justify-center"
                >
                  +
                </button>
              </div>
            </div>
          </div>
        )}

        {visibleSections.includes('time') && (
          <div className="border-t border-slate-100" />
        )}

        {/* Time Window */}
        {visibleSections.includes('time') && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Evidence recency</h4>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(TIME_PRESET_LABELS) as TimePreset[]).map((preset) => (
              <Chip key={preset} active={timePreset === preset} onClick={() => setTimePreset(preset)}>
                {TIME_PRESET_LABELS[preset]}
              </Chip>
            ))}
          </div>
          {timePreset === 'CUSTOM' && (
            <div className="grid grid-cols-2 gap-3 mt-2 p-3 bg-blue-50 rounded-lg border border-blue-100">
              <div>
                <label className="text-xs text-slate-500 mb-1 block">From</label>
                <Input type="date" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)} />
              </div>
              <div>
                <label className="text-xs text-slate-500 mb-1 block">To</label>
                <Input type="date" value={customTo} onChange={(e) => setCustomTo(e.target.value)} />
              </div>
            </div>
          )}
        </div>
        )}

        {visibleSections.includes('geography') && (
          <div className="border-t border-slate-100" />
        )}

        {/* Geography */}
        {visibleSections.includes('geography') && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Geographic focus</h4>

          {/* Selected geographies */}
          <div className="flex flex-wrap gap-2">
            {geography.map((geo) => (
              <span
                key={geo}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 text-sm text-slate-700"
              >
                <Globe className="w-3 h-3" />
                {geo === ANYWHERE_VALUE ? 'Anywhere' : geo}
                <button
                  type="button"
                  onClick={() => removeGeo(geo)}
                  className="hover:text-red-600 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>

          {/* Add geography */}
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowCountryDropdown(!showCountryDropdown)}
              className="text-xs gap-1"
            >
              <Plus className="w-3 h-3" />
              Add country or region
            </Button>

            {showCountryDropdown && (
              <div className="absolute z-10 mt-1 w-64 max-h-60 overflow-auto bg-white border border-slate-200 rounded-lg shadow-lg">
                <button
                  className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50 font-medium text-slate-700"
                  onClick={() => addGeo(ANYWHERE_VALUE)}
                >
                  Anywhere
                </button>
                <div className="px-3 py-1 text-[10px] font-semibold text-slate-400 uppercase">Regions</div>
                {SPECIAL_REGIONS.map((r) => (
                  <button
                    key={r}
                    className="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 text-slate-700"
                    onClick={() => addGeo(r)}
                  >
                    {r}
                  </button>
                ))}
                <div className="px-3 py-1 text-[10px] font-semibold text-slate-400 uppercase">Countries</div>
                {COUNTRY_LIST.map((c) => (
                  <button
                    key={c}
                    className="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-50 text-slate-700"
                    onClick={() => addGeo(c)}
                  >
                    {c}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        )}
      </div>

      {/* Confirm button */}
      <div className="px-4 py-3 bg-slate-50 border-t border-slate-200 flex justify-end">
        <Button onClick={handleConfirm} disabled={disabled || sources.length === 0}>
          {confirmLabel}
        </Button>
      </div>
    </div>
  )
}

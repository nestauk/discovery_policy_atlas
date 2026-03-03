'use client'

import React, { useState, useEffect, useMemo, useRef } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import type { TooltipItem } from 'chart.js'
import { Bar } from 'react-chartjs-2'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useAPI } from '@/lib/api'
import { useProjectDataCache } from '@/lib/projectDataCache'
import { Loader2, AlertCircle, ChevronDown, ChevronUp, Download } from 'lucide-react'

// Register once
ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend, Filler)

/** --------------------  JOBS-STYLE PALETTE -------------------- */
const PALETTE = {
  primaryNavy: '#0F294A',     // The grid (base text/axes)
  blue: '#0000FF',            // Pure blue (year chart bars)
  green: '#18A48C',           // Teal green (countries bars) 
  yellow: '#FDB633',          // Bright yellow (authors bars)
  lightGrey: '#D2C9C0',       // Energy efficiency (gridlines)
}

/** Slight alphas for fills */
const withAlpha = (hex: string, alpha = 0.85) =>
  `rgba(${parseInt(hex.slice(1,3),16)}, ${parseInt(hex.slice(3,5),16)}, ${parseInt(hex.slice(5,7),16)}, ${alpha})`

/** Title case utility function */
const toTitleCase = (str: string) => {
  // Words that should stay lowercase unless they're the first or last word
  const smallWords = new Set([
    'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'if', 'in', 'is', 'it',
    'nor', 'of', 'on', 'or', 'so', 'the', 'to', 'up', 'yet', 'with'
  ])

  return str.toLowerCase().split(' ').map((word, index, array) => {
    // Always capitalize first and last word
    if (index === 0 || index === array.length - 1) {
      return word.charAt(0).toUpperCase() + word.slice(1)
    }
    
    // Check if it's a small word
    if (smallWords.has(word)) {
      return word
    }
    
    // Capitalize everything else
    return word.charAt(0).toUpperCase() + word.slice(1)
  }).join(' ')
}

interface ProjectChartsProps { 
  projectId: string
  projectTitle?: string
  isPublic?: boolean
}
interface ChartData {
  documents_by_year: Array<{ year: number; count: number }>
  documents_by_country: Array<{ country: string; count: number }>
  documents_by_author: Array<{ author: string; count: number }>
  documents_by_institution?: Array<{ institution: string; count: number }>
  documents_by_evidence_category?: Array<{ category: string; count: number }>
}

export function ProjectCharts({ projectId, projectTitle, isPublic = false }: ProjectChartsProps) {
  type ContributorMode = 'authors' | 'institutions'
  const [chartData, setChartData] = useState<ChartData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showTimelineData, setShowTimelineData] = useState(false)
  const [showCountriesData, setShowCountriesData] = useState(false)
  const [showAuthorsData, setShowAuthorsData] = useState(false)
  const [contributorsMode, setContributorsMode] = useState<ContributorMode>('institutions')
  const [showEvidenceData, setShowEvidenceData] = useState(false)
  const { fetchWithAuth } = useAPI()
  const { getCached, setCache } = useProjectDataCache()
  const chartsLoadedProjectIdRef = useRef<string | null>(null)

  // Global minimal styling (Jobs-style: clean, high-contrast, no clutter)
  useMemo(() => {
    ChartJS.defaults.font.family = 'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial'
    ChartJS.defaults.color = PALETTE.primaryNavy
  }, [])

  useEffect(() => {
    const fetchChartData = async () => {
      if (!projectId) return

      // Skip if we've already loaded charts for this project
      if (chartsLoadedProjectIdRef.current === projectId) return

      // Check cache (survives unmount/remount on tab switch)
      const cached = getCached('charts', projectId) as ChartData | undefined
      if (cached) {
        setChartData(cached)
        setLoading(false)
        chartsLoadedProjectIdRef.current = projectId
        return
      }

      chartsLoadedProjectIdRef.current = projectId
      setLoading(true)
      setError(null)
      try {
        let data: ChartData
        if (isPublic) {
          const { getPublicProjectChartsData } = await import('@/lib/publicApi')
          data = await getPublicProjectChartsData(projectId) as ChartData
        } else {
          data = await fetchWithAuth(`/api/analysis-projects/${projectId}/charts-data`)
        }
        setChartData(data)
        setCache('charts', projectId, data)
      } catch (err) {
        console.error('Failed to fetch chart data:', err)
        setError('Failed to load chart data')
        chartsLoadedProjectIdRef.current = null
      } finally {
        setLoading(false)
      }
    }
    fetchChartData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
          <p className="text-slate-600">Loading charts...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <AlertCircle className="h-12 w-12 text-red-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-2">Error Loading Charts</h3>
          <p className="text-slate-600">{error}</p>
        </div>
      </div>
    )
  }

  if (
    !chartData ||
    (chartData.documents_by_year.length === 0 &&
      chartData.documents_by_country.length === 0 &&
      chartData.documents_by_author.length === 0)
  ) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">No data available for charts</p>
      </div>
    )
  }

  /** -------------------- Shared chart options (minimal, legible) -------------------- */
  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { intersect: false, mode: 'index' as const },
    },
    scales: {
      x: {
        grid: { display: false, borderColor: PALETTE.lightGrey },
        ticks: { 
          maxRotation: 45,
          minRotation: 0,
          autoSkip: false,
          maxTicksLimit: 15,
          font: { size: 11 }
        },
      },
      y: {
        beginAtZero: true,
        grid: { color: withAlpha(PALETTE.lightGrey, 0.4), borderColor: PALETTE.lightGrey },
        ticks: { precision: 0 },
      },
    },
  }

  // Custom options for year chart with year tooltips
  const yearChartOptions = {
    ...baseOptions,
    plugins: {
      ...baseOptions.plugins,
      tooltip: {
        intersect: false,
        mode: 'index' as const,
        callbacks: {
          title: (tooltipItems: unknown[]) => {
            const items = tooltipItems as Array<{ dataIndex: number }>
            const index = items[0].dataIndex
            return `Year: ${completeYearData.allYears?.[index]}`
          }
        }
      }
    }
  }

  // Horizontal chart options for countries and authors (no hover tooltips)
  // Create horizontal chart options dynamically with access to labels
  const createHorizontalChartOptions = (labels: string[]) => ({
    ...baseOptions,
    indexAxis: 'y' as const,
    layout: {
      padding: {
        left: 10, // Extra padding to prevent label cutoff
      }
    },
    plugins: {
      ...baseOptions.plugins,
      tooltip: { enabled: false }, // Disable tooltips since data is already labeled
    },
    scales: {
      x: {
        beginAtZero: true,
        grid: { color: withAlpha(PALETTE.lightGrey, 0.4), borderColor: PALETTE.lightGrey },
        ticks: { precision: 0 },
      },
      y: {
        grid: { display: false, borderColor: PALETTE.lightGrey },
        ticks: { 
          font: { size: 10 },
          maxRotation: 0,
          minRotation: 0,
          callback: function(value: unknown) {
            // Get the actual label from the labels array using the index
            const index = Number(value)
            const label = labels[index] || String(value)
            return label.length > 35 ? label.substring(0, 32) + '...' : label
          }
        },
      },
    },
  })

  /** -------------------- Data -------------------- */
  // Fill in missing years for complete timeline
  const createCompleteYearData = () => {
    if (chartData.documents_by_year.length === 0) return { labels: [], data: [] }
    
    const minYear = Math.min(...chartData.documents_by_year.map(d => d.year))
    const maxYear = Math.max(...chartData.documents_by_year.map(d => d.year))
    const allYears = Array.from({length: maxYear - minYear + 1}, (_, i) => minYear + i)
    const yearSpan = maxYear - minYear + 1
    
    const yearData = allYears.map(year => {
      const found = chartData.documents_by_year.find(d => d.year === year)
      return found ? found.count : 0
    })
    
    // Smart label sampling for long timelines (>20 years)
    const createSmartLabels = () => {
      if (yearSpan <= 20) {
        // Show all years for short timelines
        return allYears.map(year => year.toString())
      } else {
        // Show strategic years: first, last, and every 5th year that ends in 0 or 5
        return allYears.map((year, index) => {
          const isFirst = index === 0
          const isLast = index === allYears.length - 1
          const isRoundYear = year % 5 === 0 && year % 10 !== 0 // ends in 5
          const isDecade = year % 10 === 0 // ends in 0
          
          // Skip first year if it's too close to a round year
          if (isFirst && !isLast) {
            const nextRoundYear = allYears.find(y => y % 5 === 0)
            if (nextRoundYear && nextRoundYear - year <= 2) {
              return ''
            }
          }
          
          if (isFirst || isLast || isDecade || isRoundYear) {
            return year.toString()
          }
          return ''
        })
      }
    }
    
    return {
      labels: createSmartLabels(),
      data: yearData,
      allYears: allYears // Keep full year data for tooltips
    }
  }

  const completeYearData = createCompleteYearData()

  // Individual chart export functions with descriptive filenames
  const createFilename = (type: string) => {
    const now = new Date()
    const time = now.toTimeString().slice(0, 5).replace(':', 'h')
    const date = now.toLocaleDateString('en-GB').replace(/\//g, '')
    
    // Create research question slug from project title
    const researchSlug = projectTitle
      ? toTitleCase(projectTitle.replace(/^Chat Search:\s*/, ''))
          .toLowerCase()
          .replace(/[^a-z0-9\s]/g, '')
          .replace(/\s+/g, '_')
          .substring(0, 50) // Keep reasonable length
      : 'research_data'
    
    return `${researchSlug}_${type}_${time}_${date}.csv`
  }

  const exportTimelineData = () => {
    const csvData = ['Year,Documents']
    completeYearData.allYears?.forEach((year, index) => {
      csvData.push(`${year},${completeYearData.data[index]}`)
    })
    
    const csvContent = csvData.join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.setAttribute('href', url)
    link.setAttribute('download', createFilename('documents_over_time'))
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const exportCountriesData = () => {
    const csvData = ['Country,Documents']
    chartData.documents_by_country.forEach(item => {
      csvData.push(`"${item.country}",${item.count}`)
    })
    
    const csvContent = csvData.join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.setAttribute('href', url)
    link.setAttribute('download', createFilename('countries_data'))
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const exportContributorsData = () => {
    const usingInstitutions = contributorsMode === 'institutions'
    const rows = usingInstitutions
      ? (chartData.documents_by_institution || [])
      : chartData.documents_by_author
    const label = usingInstitutions ? 'Institution' : 'Author'
    const csvData = [`${label},Documents`]
    rows.forEach((item) => {
      const key = usingInstitutions
        ? (item as { institution: string }).institution
        : (item as { author: string }).author
      csvData.push(`"${key}",${item.count}`)
    })

    const csvContent = csvData.join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.setAttribute('href', url)
    link.setAttribute(
      'download',
      createFilename(usingInstitutions ? 'institutions_data' : 'authors_data')
    )
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const exportEvidenceData = () => {
    if (!chartData.documents_by_evidence_category) return
    const csvData = ['Evidence Category,Documents']
    chartData.documents_by_evidence_category.forEach(item => {
      csvData.push(`"${item.category}",${item.count}`)
    })

    const csvContent = csvData.join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.setAttribute('href', url)
    link.setAttribute('download', createFilename('evidence_categories'))
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }
  
  const yearChartData = {
    labels: completeYearData.labels as string[],
    datasets: [
      {
        label: 'Documents per Year',
        data: completeYearData.data as number[],
        backgroundColor: withAlpha(PALETTE.blue, 0.85),
        borderColor: PALETTE.blue,
        borderWidth: 1,
        borderRadius: 6,
      },
    ],
  }

  const countryChartData = {
    labels: chartData.documents_by_country.map((d) => d.country) as string[],
    datasets: [
      {
        label: 'Documents per Country',
        data: chartData.documents_by_country.map((d) => d.count) as number[],
        backgroundColor: withAlpha(PALETTE.green, 0.85),
        borderColor: PALETTE.green,
        borderWidth: 1,
        borderRadius: 6,
      },
    ],
  }

  const contributorRows =
    contributorsMode === 'institutions'
      ? (chartData.documents_by_institution || [])
      : chartData.documents_by_author
  const contributorLabels = contributorRows.map((d) =>
    contributorsMode === 'institutions'
      ? (d as { institution: string }).institution
      : (d as { author: string }).author
  )
  const contributorChartData = {
    labels: contributorLabels as string[],
    datasets: [
      {
        label:
          contributorsMode === 'institutions'
            ? 'Documents per Institution'
            : 'Documents per Author',
        data: contributorRows.map((d) => d.count) as number[],
        backgroundColor: withAlpha(PALETTE.yellow, 0.85),
        borderColor: PALETTE.yellow,
        borderWidth: 1,
        borderRadius: 6,
      },
    ],
  }

  // Evidence category colors (dark = strong evidence, light = weak evidence)
  // Removed "Other" - it's filtered out at the backend
  const evidenceCategoryColors: Record<string, string> = {
    'Systematic Review and Meta-Analysis': '#0F294A',      // Navy (strongest)
    'RCTs and Quasi-Experimental Studies': '#9A1BBE',     // Purple
    'Observational Research Studies': '#0000FF',          // Blue
    'Modelling & Simulation': '#18A48C',                  // Green
    'Policy Syntheses & Guidance Documents': '#97D9E3',   // Aqua
    'Qualitative & Contextual Evidence': '#A59BEE',       // Violet
    'Expert Opinion and Commentary': '#F6A4B7',           // Pink
    'Unknown / Insufficient information': '#f8f5f4',      // Light grey (weakest)
  }

  // Evidence category short names for chart display
  // Removed "Other" - it's filtered out at the backend
  const evidenceCategoryShortNames: Record<string, string> = {
    'Systematic Review and Meta-Analysis': 'Systematic Review',
    'RCTs and Quasi-Experimental Studies': 'RCT/Quasi-Exp',
    'Observational Research Studies': 'Observational',
    'Modelling & Simulation': 'Modelling',
    'Policy Syntheses & Guidance Documents': 'Policy Guidance',
    'Qualitative & Contextual Evidence': 'Qualitative',
    'Expert Opinion and Commentary': 'Expert Opinion',
    'Unknown / Insufficient information': 'Unknown',
  }

  // Evidence category chart data - stacked horizontal bar
  const evidenceCategoryChartData = chartData.documents_by_evidence_category ? {
    labels: ['Evidence Distribution'],
    datasets: chartData.documents_by_evidence_category.map((item) => ({
      label: evidenceCategoryShortNames[item.category] || item.category,
      data: [item.count],
      backgroundColor: evidenceCategoryColors[item.category] || '#646363',
      borderWidth: 0,
    }))
  } : null

  // Calculate total for evidence category chart max value
  const evidenceTotalDocs = evidenceCategoryChartData
    ? evidenceCategoryChartData.datasets.reduce((sum, dataset) => sum + dataset.data[0], 0)
    : 0

  const evidenceCategoryOptions = {
    indexAxis: 'y' as const,
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        position: 'bottom' as const,
        labels: {
          boxWidth: 12,
          boxHeight: 12,
          padding: 8,
          font: { size: 10 },
          generateLabels: (chart: unknown) => {
            const chartData = (chart as { data: typeof evidenceCategoryChartData | null }).data
            if (!chartData) return []
            return chartData.datasets.map((dataset, i) => ({
              text: `${dataset.label} (${dataset.data[0]})`,
              fillStyle: dataset.backgroundColor as string,
              hidden: false,
              index: i,
            }))
          }
        }
      },
      tooltip: {
        callbacks: {
          label: (context: TooltipItem<'bar'>) => {
            const value = context.parsed.x ?? 0
            return `${context.dataset.label || 'Unknown'}: ${value} documents`
          }
        }
      }
    },
    scales: {
      x: {
        stacked: true,
        beginAtZero: true,
        max: evidenceTotalDocs || undefined, // Set max to total so bar fills width
        grid: { display: false },
        ticks: { display: false },
      },
      y: {
        stacked: true,
        grid: { display: false },
        ticks: { display: false },
      },
    },
  }

  return (
    <div className="space-y-6">

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {chartData.documents_by_year.length > 0 && (
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Published documents over time</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="h-80">
                <Bar data={yearChartData} options={yearChartOptions} />
              </div>
              
              {/* Collapsible data section */}
              <div className="border-t border-slate-100 pt-3">
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => setShowTimelineData(!showTimelineData)}
                    className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-700 transition-colors"
                  >
                    {showTimelineData ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    View data
                  </button>
                  <button
                    onClick={exportTimelineData}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-50 rounded transition-colors"
                  >
                    <Download className="h-3 w-3" />
                    Export
                  </button>
                </div>
                
                {showTimelineData && (
                  <div className="mt-3 max-h-64 overflow-y-auto border border-slate-200 rounded-md">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 sticky top-0">
                        <tr>
                          <th className="text-left py-2 px-3 font-medium text-slate-700">Year</th>
                          <th className="text-right py-2 px-3 font-medium text-slate-700">Documents</th>
                        </tr>
                      </thead>
                      <tbody>
                        {completeYearData.allYears?.map((year, index) => (
                          <tr key={year} className="border-t border-slate-100 hover:bg-slate-25">
                            <td className="py-1.5 px-3 select-text font-mono text-slate-700">{year}</td>
                            <td className="py-1.5 px-3 text-right text-slate-600">{completeYearData.data[index]}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {chartData.documents_by_country.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>
                Top {chartData.documents_by_country.length} {chartData.documents_by_country.length === 1 ? 'country' : 'countries'}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="h-80">
                <Bar data={countryChartData} options={createHorizontalChartOptions(chartData.documents_by_country.map(d => d.country))} />
              </div>
              
              {/* Collapsible data section */}
              <div className="border-t border-slate-100 pt-3">
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => setShowCountriesData(!showCountriesData)}
                    className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-700 transition-colors"
                  >
                    {showCountriesData ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    View data
                  </button>
                  <button
                    onClick={exportCountriesData}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-50 rounded transition-colors"
                  >
                    <Download className="h-3 w-3" />
                    Export
                  </button>
                </div>
                
                {showCountriesData && (
                  <div className="mt-3 grid gap-1 text-xs">
                    {chartData.documents_by_country.map((item) => (
                      <div key={item.country} className="flex justify-between items-center py-1 hover:bg-slate-50 px-2 -mx-2 rounded">
                        <span className="select-text font-mono text-slate-700">{item.country}</span>
                        <span className="text-slate-400">{item.count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {((chartData.documents_by_institution || []).length > 0 || chartData.documents_by_author.length > 0) && (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle>
                  Top {contributorRows.length}{' '}
                  {contributorsMode === 'institutions'
                    ? contributorRows.length === 1
                      ? 'institution'
                      : 'institutions'
                    : contributorRows.length === 1
                      ? 'author'
                      : 'authors'}
                </CardTitle>
                <div className="inline-flex rounded-md border border-slate-200 p-0.5">
                  <button
                    onClick={() => setContributorsMode('institutions')}
                    className={`rounded px-2 py-1 text-xs ${
                      contributorsMode === 'institutions'
                        ? 'bg-slate-100 text-slate-900'
                        : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    Institutions
                  </button>
                  <button
                    onClick={() => setContributorsMode('authors')}
                    className={`rounded px-2 py-1 text-xs ${
                      contributorsMode === 'authors'
                        ? 'bg-slate-100 text-slate-900'
                        : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    Authors
                  </button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="h-80">
                <Bar data={contributorChartData} options={createHorizontalChartOptions(contributorLabels)} />
              </div>
              
              {/* Collapsible data section */}
              <div className="border-t border-slate-100 pt-3">
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => setShowAuthorsData(!showAuthorsData)}
                    className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-700 transition-colors"
                  >
                    {showAuthorsData ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    View data
                  </button>
                  <button
                    onClick={exportContributorsData}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-50 rounded transition-colors"
                  >
                    <Download className="h-3 w-3" />
                    Export
                  </button>
                </div>
                
                {showAuthorsData && (
                  <div className="mt-3 grid gap-1 text-xs">
                    {contributorRows.map((item) => {
                      const label = contributorsMode === 'institutions'
                        ? (item as { institution: string }).institution
                        : (item as { author: string }).author
                      return (
                      <div key={label} className="flex justify-between items-center py-1 hover:bg-slate-50 px-2 -mx-2 rounded">
                        <span className="select-text font-mono text-slate-700">{label}</span>
                        <span className="text-slate-400">{item.count}</span>
                      </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {evidenceCategoryChartData && chartData.documents_by_evidence_category && chartData.documents_by_evidence_category.length > 0 && (
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Evidence Category Distribution</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="h-24">
                <Bar data={evidenceCategoryChartData} options={evidenceCategoryOptions} />
              </div>

              {/* Collapsible data section */}
              <div className="border-t border-slate-100 pt-3">
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => setShowEvidenceData(!showEvidenceData)}
                    className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-700 transition-colors"
                  >
                    {showEvidenceData ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    View data
                  </button>
                  <button
                    onClick={exportEvidenceData}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-50 rounded transition-colors"
                  >
                    <Download className="h-3 w-3" />
                    Export
                  </button>
                </div>

                {showEvidenceData && (
                  <div className="mt-3 grid gap-1 text-xs">
                    {chartData.documents_by_evidence_category.map((item) => {
                      const color = evidenceCategoryColors[item.category] || '#646363'
                      return (
                        <div key={item.category} className="flex justify-between items-center py-1 hover:bg-slate-50 px-2 -mx-2 rounded">
                          <div className="flex items-center gap-2">
                            <div
                              className="w-3 h-3 rounded"
                              style={{ backgroundColor: color }}
                            />
                            <span className="select-text font-mono text-slate-700">{item.category}</span>
                          </div>
                          <span className="text-slate-400">{item.count}</span>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
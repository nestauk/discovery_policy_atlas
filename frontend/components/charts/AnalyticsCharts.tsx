'use client'

import React from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
} from 'chart.js'
import { Bar, Doughnut } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement
)

interface AnalyticsData {
  total_papers: number
  countries: Record<string, number>
  years: Record<string, number>
  journals: Record<string, number>
  authors: Record<string, number>
  document_types: Record<string, number>
  confidence_levels: Record<string, number>
  generated_at: string
}

interface AnalyticsChartsProps {
  analytics: AnalyticsData
}

export function AnalyticsCharts({ analytics }: AnalyticsChartsProps) {
  if (!analytics || analytics.total_papers === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-gray-500">No analytics data available</p>
      </div>
    )
  }

  // Prepare data for countries chart
  const countriesData = {
    labels: Object.keys(analytics.countries),
    datasets: [
      {
        label: 'Papers per Country',
        data: Object.values(analytics.countries),
        backgroundColor: 'rgba(59, 130, 246, 0.8)',
        borderColor: 'rgba(59, 130, 246, 1)',
        borderWidth: 1,
      },
    ],
  }

  // Prepare data for years chart
  const yearsData = {
    labels: Object.keys(analytics.years).sort(),
    datasets: [
      {
        label: 'Papers per Year',
        data: Object.keys(analytics.years).sort().map(year => analytics.years[year]),
        backgroundColor: 'rgba(34, 197, 94, 0.8)',
        borderColor: 'rgba(34, 197, 94, 1)',
        borderWidth: 1,
      },
    ],
  }

  // Prepare data for confidence levels chart
  const confidenceData = {
    labels: Object.keys(analytics.confidence_levels),
    datasets: [
      {
        label: 'Papers by Confidence Level',
        data: Object.values(analytics.confidence_levels),
        backgroundColor: [
          'rgba(239, 68, 68, 0.8)',   // Red for low
          'rgba(245, 158, 11, 0.8)',  // Orange for medium
          'rgba(59, 130, 246, 0.8)',  // Blue for high
          'rgba(34, 197, 94, 0.8)',   // Green for very high
        ],
        borderColor: [
          'rgba(239, 68, 68, 1)',
          'rgba(245, 158, 11, 1)',
          'rgba(59, 130, 246, 1)',
          'rgba(34, 197, 94, 1)',
        ],
        borderWidth: 1,
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top' as const,
      },
    },
    scales: {
      y: {
        beginAtZero: true,
      },
    },
  }

  const doughnutOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'bottom' as const,
      },
    },
  }

  return (
    <div className="space-y-8">
      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-blue-50 p-4 rounded-lg">
          <h3 className="text-lg font-semibold text-blue-900">{analytics.total_papers}</h3>
          <p className="text-blue-600">Total Papers</p>
        </div>
        <div className="bg-green-50 p-4 rounded-lg">
          <h3 className="text-lg font-semibold text-green-900">{Object.keys(analytics.countries).length}</h3>
          <p className="text-green-600">Countries</p>
        </div>
        <div className="bg-purple-50 p-4 rounded-lg">
          <h3 className="text-lg font-semibold text-purple-900">{Object.keys(analytics.years).length}</h3>
          <p className="text-purple-600">Years</p>
        </div>
        <div className="bg-orange-50 p-4 rounded-lg">
          <h3 className="text-lg font-semibold text-orange-900">{Object.keys(analytics.journals).length}</h3>
          <p className="text-orange-600">Journals</p>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Countries Chart */}
        <div className="bg-white p-6 rounded-lg border">
          <h3 className="text-lg font-semibold mb-4">Papers by Country</h3>
          <Bar data={countriesData} options={chartOptions} />
        </div>

        {/* Years Chart */}
        <div className="bg-white p-6 rounded-lg border">
          <h3 className="text-lg font-semibold mb-4">Papers by Year</h3>
          <Bar data={yearsData} options={chartOptions} />
        </div>

        {/* Confidence Levels Chart */}
        <div className="bg-white p-6 rounded-lg border">
          <h3 className="text-lg font-semibold mb-4">Papers by Confidence Level</h3>
          <Doughnut data={confidenceData} options={doughnutOptions} />
        </div>

        {/* Top Journals */}
        <div className="bg-white p-6 rounded-lg border">
          <h3 className="text-lg font-semibold mb-4">Top Journals</h3>
          <div className="space-y-2">
            {Object.entries(analytics.journals)
              .sort(([,a], [,b]) => b - a)
              .slice(0, 5)
              .map(([journal, count]) => (
                <div key={journal} className="flex justify-between items-center">
                  <span className="text-sm text-gray-600 truncate">{journal}</span>
                  <span className="text-sm font-medium">{count}</span>
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* Generated timestamp */}
      <div className="text-xs text-gray-500 text-center">
        Analytics generated on {new Date(analytics.generated_at).toLocaleString()}
      </div>
    </div>
  )
} 
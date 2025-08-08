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
import { Bar } from 'react-chartjs-2'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
// import { Badge } from '@/components/ui/badge'
import { Paper } from '@/types/search'

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement
)

interface SimpleAnalyticsProps {
  papers: Paper[]
}

export function SimpleAnalytics({ papers }: SimpleAnalyticsProps) {
  if (!papers || papers.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-gray-500">No papers available for analytics</p>
      </div>
    )
  }

  // Calculate statistics from papers
  const calculateStats = () => {
    const countries: Record<string, number> = {}
    const years: Record<string, number> = {}
    const confidenceLevels: Record<string, number> = {}
    const sourceTypes: Record<string, number> = {}
    
    papers.forEach(paper => {
      // Countries
      if (paper.source_country && paper.source_country.trim()) {
        const country = paper.source_country.trim()
        countries[country] = (countries[country] || 0) + 1
      }
      
      // Years
      if (paper.publication_year && paper.publication_year > 1900 && paper.publication_year <= new Date().getFullYear()) {
        years[paper.publication_year.toString()] = (years[paper.publication_year.toString()] || 0) + 1
      }
      
      // Confidence levels
      if (paper.confidence !== undefined && paper.confidence !== null) {
        let level = 'Unknown'
        if (paper.confidence >= 0.9) level = 'Very High (90%+)'
        else if (paper.confidence >= 0.8) level = 'High (80-89%)'
        else if (paper.confidence >= 0.7) level = 'Medium-High (70-79%)'
        else if (paper.confidence >= 0.6) level = 'Medium (60-69%)'
        else if (paper.confidence >= 0.5) level = 'Low (50-59%)'
        else level = 'Very Low (<50%)'
        
        confidenceLevels[level] = (confidenceLevels[level] || 0) + 1
      }
      
      // Source types
      if (paper.source_type && paper.source_type.trim()) {
        const sourceType = paper.source_type.trim()
        sourceTypes[sourceType] = (sourceTypes[sourceType] || 0) + 1
      }
    })
    
    return { countries, years, confidenceLevels, sourceTypes }
  }

  const stats = calculateStats()
  // const totalPapers = papers.length
  // const relevantPapers = papers.filter(p => p.is_relevant).length
  // Keep for future use in additional metrics
  // const papersWithConfidence = papers.filter(p => p.confidence !== undefined && p.confidence !== null)
  // const avgConfidence = papersWithConfidence.length > 0 
  //   ? papersWithConfidence.reduce((sum, p) => sum + (p.confidence || 0), 0) / papersWithConfidence.length 
  //   : 0

  // Prepare chart data
  const sortedCountries = Object.entries(stats.countries)
    .sort(([,a], [,b]) => b - a) // Sort by count descending
  
  const countriesData = {
    labels: sortedCountries.map(([country]) => country),
    datasets: [{
      label: 'Papers per Country',
      data: sortedCountries.map(([,count]) => count),
      backgroundColor: 'rgba(59, 130, 246, 0.8)',
      borderColor: 'rgba(59, 130, 246, 1)',
      borderWidth: 1,
    }],
  }

  const yearsData = {
    labels: Object.keys(stats.years).sort(),
    datasets: [{
      label: 'Papers per Year',
      data: Object.keys(stats.years).sort().map(year => stats.years[year]),
      backgroundColor: 'rgba(34, 197, 94, 0.8)',
      borderColor: 'rgba(34, 197, 94, 1)',
      borderWidth: 1,
    }],
  }

  // const confidenceData = {
  //   labels: Object.keys(stats.confidenceLevels),
  //   datasets: [{
  //     label: 'Papers by Confidence',
  //     data: Object.values(stats.confidenceLevels),
  //     backgroundColor: [
  //       'rgba(239, 68, 68, 0.8)',
  //       'rgba(245, 158, 11, 0.8)',
  //       'rgba(59, 130, 246, 0.8)',
  //       'rgba(34, 197, 94, 0.8)',
  //       'rgba(107, 114, 128, 0.8)',
  //     ],
  //     borderColor: [
  //       'rgba(239, 68, 68, 1)',
  //       'rgba(245, 158, 11, 1)',
  //       'rgba(59, 130, 246, 1)',
  //       'rgba(34, 197, 94, 1)',
  //       'rgba(107, 114, 128, 1)',
  //     ],
  //     borderWidth: 1,
  //   }],
  // }

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

  // const doughnutOptions = {
  //   responsive: true,
  //   plugins: {
  //     legend: {
  //       position: 'bottom' as const,
  //     },
  //   },
  // }

  return (
    <div className="space-y-6">
      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Countries Chart */}
        {Object.keys(stats.countries).length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Papers by Country</CardTitle>
            </CardHeader>
            <CardContent>
              <Bar data={countriesData} options={chartOptions} />
            </CardContent>
          </Card>
        )}

        {/* Years Chart */}
        {Object.keys(stats.years).length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Papers by Year</CardTitle>
            </CardHeader>
            <CardContent>
              <Bar data={yearsData} options={chartOptions} />
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
} 
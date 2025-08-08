'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { useAPI } from '@/lib/api'
import { PapersTable } from '@/components/search/papers-table'
import { ViewToggle } from '@/components/search/view-toggle'
import { Paper } from '@/types/search'
import { useProjectStore } from '@/lib/projectStore'
import { 
  FileText, 
  Search, 
  TrendingUp,
  Lightbulb,
  ChevronDown,
  Bot,
  Quote,
  AlertTriangle,
  RefreshCw,
  FolderOpen,
  BookOpen
} from 'lucide-react'
import { ChatbotWidget } from '@/components/chatbot/ChatbotWidget'
import { ChatInterface } from '@/components/chatbot/ChatInterface'
// import { AnalyticsCharts } from '@/components/charts/AnalyticsCharts'
import { useChatbotStore } from '@/lib/chatbotStore'
import { SimpleAnalytics } from '@/components/charts/SimpleAnalytics'

// Dev utils are loaded globally in development mode via devUtils.ts

// Key Insights Display Component
interface KeyInsightsDisplayProps {
  insights: {
    extraction: {
      insights: Array<{
        insight: string;
        confidence: number;
        evidence_source: string;
        supporting_quotes: string[];
      }>;
      methodology?: string;
      evidence_coverage?: string;
    };
    review?: {
      approved: boolean;
      score: number;
    };
    query?: string;
    extracted_at?: string;
    quality_score?: number;
  };
}

function KeyInsightsDisplay({ insights }: KeyInsightsDisplayProps) {
  const [expandedInsight, setExpandedInsight] = useState<number | null>(null);

  if (!insights || !insights.extraction) {
    return (
      <div className="text-center py-4">
        <p className="text-gray-500">No insights data available</p>
      </div>
    );
  }

  const { extraction } = insights;
  const insightsList = extraction.insights || [];

  // const getConfidenceColor = (confidence: number) => {
  //   if (confidence >= 0.8) return 'bg-green-100 text-green-800';
  //   if (confidence >= 0.6) return 'bg-yellow-100 text-yellow-800';
  //   return 'bg-red-100 text-red-800';
  // };

  // const formatDate = (dateString: string) => {
  //   try {
  //     return new Date(dateString).toLocaleDateString('en-US', {
  //       year: 'numeric',
  //       month: 'short',
  //       day: 'numeric',
  //       hour: '2-digit',
  //       minute: '2-digit'
  //     });
  //   } catch {
  //     return dateString;
  //   }
  // };

  return (
    <div className="space-y-6">
      {/* Header with metadata */}
      {/* <div className="bg-gray-50 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-medium text-gray-900">Analysis Overview</h4>
          <div className="flex items-center gap-2">
            {review.approved ? (
              <CheckCircle className="h-4 w-4 text-green-600" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-yellow-600" />
            )}
            <Badge variant="outline">
              Quality: {(quality_score * 100).toFixed(0)}%
            </Badge>
          </div>
        </div>
        <p className="text-sm text-gray-600 mb-2">
          <strong>Query:</strong> {query}
        </p>
        <p className="text-sm text-gray-500">
          Extracted on {formatDate(extracted_at)} • {insightsList.length} insights
        </p>
      </div> */}

      {/* Insights List */}
      <div className="space-y-4">
        {insightsList.map((insight: {
        insight: string;
        confidence: number;
        evidence_source: string;
        supporting_quotes: string[];
      }, index: number) => {
          const isExpanded = expandedInsight === index;
          
          return (
            <div key={index} className="border rounded-lg p-4 hover:bg-gray-50 transition-colors">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                  <span className="text-blue-600 font-medium text-sm">{index + 1}</span>
                </div>
                
                <div className="flex-1">
                  <div className="flex items-start justify-between gap-4">
                    <p className="text-slate-700 leading-relaxed font-medium">
                      {insight.insight}
                    </p>
                    {/* <Badge className={getConfidenceColor(insight.confidence)}>
                      {(insight.confidence * 100).toFixed(0)}%
                    </Badge> */}
                  </div>
                  
                  <div className="mt-2 text-sm text-gray-600">
                    <strong>Source:</strong> {insight.evidence_source}
                  </div>

                  {/* Supporting quotes - expandable */}
                  {insight.supporting_quotes && insight.supporting_quotes.length > 0 && (
                    <div className="mt-3">
                      <button
                        onClick={() => setExpandedInsight(isExpanded ? null : index)}
                        className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800"
                      >
                        <Quote className="h-3 w-3" />
                        {insight.supporting_quotes.length} supporting quote{insight.supporting_quotes.length !== 1 ? 's' : ''}
                        <ChevronDown className={`h-3 w-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                      </button>
                      
                      {isExpanded && (
                        <div className="mt-2 space-y-2">
                          {insight.supporting_quotes.map((quote: string, qIdx: number) => (
                            <div key={qIdx} className="bg-blue-50 border-l-4 border-blue-200 p-3 rounded">
                              <p className="text-sm italic text-gray-700">&ldquo;{quote}&rdquo;</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Methodology footer */}
      {/* {extraction.methodology && (
        <div className="border-t pt-4">
          <details className="text-sm">
            <summary className="cursor-pointer text-gray-600 hover:text-gray-800 font-medium">
              Methodology & Evidence Coverage
            </summary>
            <div className="mt-2 space-y-2 text-gray-600">
              <p><strong>Methodology:</strong> {extraction.methodology}</p>
              <p><strong>Evidence Coverage:</strong> {extraction.evidence_coverage}</p>
            </div>
          </details>
        </div>
      )} */}
    </div>
  );
}

// Policy Recommendations Display Component
interface PolicyRecommendationsDisplayProps {
  recommendations: {
    recommendations: {
      recommendations: Array<{
        recommendation: string;
        rationale: string;
        evidence_strength: string;
        implementation_considerations: string[];
        supporting_insights: string[];
      }>;
      overall_assessment?: string;
      gaps_identified?: string[];
    };
    review?: {
      approved: boolean;
      score: number;
    };
    query?: string;
    generated_at?: string;
    quality_score?: number;
  };
}

function PolicyRecommendationsDisplay({ recommendations }: PolicyRecommendationsDisplayProps) {
  const [expandedRecommendation, setExpandedRecommendation] = useState<number | null>(null);

  if (!recommendations || !recommendations.recommendations) {
    return (
      <div className="text-center py-4">
        <p className="text-gray-500">No recommendations data available</p>
      </div>
    );
  }

  const { recommendations: recs } = recommendations;
  const recommendationsList = recs.recommendations || [];

  // const formatDate = (dateString: string) => {
  //   try {
  //     return new Date(dateString).toLocaleDateString('en-US', {
  //       year: 'numeric',
  //       month: 'short',
  //       day: 'numeric',
  //       hour: '2-digit',
  //       minute: '2-digit'
  //     });
  //   } catch {
  //     return dateString;
  //   }
  // };

  return (
    <div className="space-y-6">
      {/* Header with metadata */}
      {/* <div className="bg-gray-50 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-medium text-gray-900">Policy Analysis Overview</h4>
          <div className="flex items-center gap-2">
            {review.approved ? (
              <CheckCircle className="h-4 w-4 text-green-600" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-yellow-600" />
            )}
            <Badge variant="outline">
              Quality: {(quality_score * 100).toFixed(0)}%
            </Badge>
          </div>
        </div>
        <p className="text-sm text-gray-600 mb-2">
          <strong>Query:</strong> {query}
        </p>
        <p className="text-sm text-gray-500">
          Generated on {formatDate(generated_at)} • {recommendationsList.length} recommendations
        </p>
      </div> */}

      {/* Recommendations List */}
      <div className="space-y-4">
        {recommendationsList.map((rec: {
          recommendation: string;
          rationale: string;
          evidence_strength: string;
          implementation_considerations: string[];
          supporting_insights: string[];
        }, index: number) => {
          const isExpanded = expandedRecommendation === index;
          
          return (
            <Card 
              key={index} 
              className="border border-slate-200 bg-white cursor-pointer hover:shadow-md transition-shadow"
              onClick={() => setExpandedRecommendation(isExpanded ? null : index)}
            >
              <CardContent className="p-4">
                <div className="flex items-start gap-4">
                  <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-white font-semibold text-sm">
                      {index + 1}
                    </span>
                  </div>
                  
                  <div className="flex-1">
                    <p className="text-slate-900 leading-relaxed font-medium mb-2">
                      {rec.recommendation}
                    </p>
                    
                    {/* {rec.evidence_strength && (
                      <div className="mb-2">
                        <Badge variant="outline" className="text-xs">
                          Evidence: {rec.evidence_strength}
                        </Badge>
                      </div>
                    )} */}

                    {isExpanded && (
                      <div className="mt-4 space-y-3 border-t pt-3">
                        {rec.rationale && (
                          <div>
                            <h5 className="font-medium text-sm text-gray-700 mb-1">Rationale</h5>
                            <p className="text-sm text-gray-600">{rec.rationale}</p>
                          </div>
                        )}
                        
                        {rec.implementation_considerations && rec.implementation_considerations.length > 0 && (
                          <div>
                            <h5 className="font-medium text-sm text-gray-700 mb-1">Implementation Considerations</h5>
                            <ul className="text-sm text-gray-600 space-y-1">
                              {rec.implementation_considerations.map((consideration: string, idx: number) => (
                                <li key={idx} className="flex items-start gap-2">
                                  <span className="w-1 h-1 bg-gray-400 rounded-full mt-2 flex-shrink-0"></span>
                                  {consideration}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        
                        {rec.supporting_insights && rec.supporting_insights.length > 0 && (
                          <div>
                            <h5 className="font-medium text-sm text-gray-700 mb-1">Supporting Insights</h5>
                            <ul className="text-sm text-gray-600 space-y-1">
                              {rec.supporting_insights.map((insight: string, idx: number) => (
                                <li key={idx} className="flex items-start gap-2">
                                  <span className="w-1 h-1 bg-blue-400 rounded-full mt-2 flex-shrink-0"></span>
                                  {insight}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  
                  <div className="flex-shrink-0">
                    <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Overall Assessment */}
      {/* {recs.overall_assessment && (
        <div className="border-t pt-4">
          <details className="text-sm">
            <summary className="cursor-pointer text-gray-600 hover:text-gray-800 font-medium">
              Overall Assessment & Evidence Gaps
            </summary>
            <div className="mt-2 space-y-2 text-gray-600">
              <p><strong>Overall Assessment:</strong> {recs.overall_assessment}</p>
              {recs.gaps_identified && recs.gaps_identified.length > 0 && (
                <div>
                  <strong>Evidence Gaps:</strong>
                  <ul className="list-disc list-inside mt-1">
                    {recs.gaps_identified.map((gap: string, idx: number) => (
                      <li key={idx}>{gap}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </details>
        </div>
      )} */}
    </div>
  );
}

// Executive Brief Display Component
interface ExecutiveBriefDisplayProps {
  brief: {
    brief: {
      executive_summary: string;
      key_findings: string[];
      policy_priorities: string[];
      evidence_strength: string;
      next_steps: string[];
    };
    query?: string;
    generated_at?: string;
  };
}

function ExecutiveBriefDisplay({ brief, papers }: ExecutiveBriefDisplayProps & { papers?: Paper[] }) {
  if (!brief || !brief.brief) {
    return (
      <div className="text-center py-4">
        <p className="text-gray-500">No executive brief available</p>
      </div>
    );
  }

  const { brief: briefData } = brief;

  // Function to calculate country statistics from papers
  const getCountryStats = (papers: Paper[]) => {
    const countries: Record<string, number> = {}
    
    papers.forEach(paper => {
      if (paper.source_country && paper.source_country.trim()) {
        const country = paper.source_country.trim()
        countries[country] = (countries[country] || 0) + 1
      }
    })
    
    const sortedCountries = Object.entries(countries)
      .sort(([,a], [,b]) => b - a)
      .slice(0, 3)
    
    return {
      totalCountries: Object.keys(countries).length,
      topCountries: sortedCountries
    }
  }

  // const formatDate = (dateString: string) => {
  //   try {
  //     return new Date(dateString).toLocaleDateString('en-US', {
  //       year: 'numeric',
  //       month: 'short',
  //       day: 'numeric',
  //       hour: '2-digit',
  //       minute: '2-digit'
  //     });
  //   } catch {
  //     return dateString;
  //   }
  // };

  return (
    <div className="space-y-6">
      {/* Header */}
      {/* <div className="border-b pb-4">
        <h3 className="text-xl font-semibold text-gray-900 mb-2">Executive Brief</h3>
        <p className="text-sm text-gray-600">
          <strong>Subject:</strong> {query}
        </p>
        <p className="text-sm text-gray-500">
          Generated on {formatDate(generated_at)}
        </p>
      </div> */}

      {/* Executive Summary */}
      <div>
        {/* <h4 className="font-semibold text-gray-900 mb-3">Executive Summary</h4> */}
        <p className="text-gray-700 leading-relaxed font-normal">{briefData.executive_summary}</p>
      </div>

      {/* Key Findings */}
      <div>
        <h4 className="font-semibold text-gray-900 mb-3">Key Findings</h4>
        <ul className="space-y-2">
          {briefData.key_findings.map((finding: string, idx: number) => (
            <li key={idx} className="flex items-start gap-3">
              <span className="w-2 h-2 bg-blue-600 rounded-full mt-2 flex-shrink-0"></span>
              <span className="text-gray-700 font-normal leading-relaxed">{finding}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Policy Priorities */}
      <div>
        <h4 className="font-semibold text-gray-900 mb-3">Policy Priorities</h4>
        <ul className="space-y-2">
          {briefData.policy_priorities.map((priority: string, idx: number) => (
            <li key={idx} className="flex items-start gap-3">
              <span className="w-6 h-6 bg-green-100 text-green-700 rounded-full flex items-center justify-center text-sm font-medium flex-shrink-0">
                {idx + 1}
              </span>
              <span className="text-gray-700 font-normal leading-relaxed">{priority}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Evidence Strength */}
      <div>
        <h4 className="font-semibold text-gray-900 mb-3">Evidence Strength</h4>
        <p className="text-gray-700 font-normal leading-relaxed">{briefData.evidence_strength}</p>
      </div>

      {/* Next Steps */}
      <div>
        <h4 className="font-semibold text-gray-900 mb-3">Recommended Next Steps</h4>
        <ul className="space-y-2">
          {briefData.next_steps.map((step: string, idx: number) => (
            <li key={idx} className="flex items-start gap-3">
              <span className="w-6 h-6 bg-orange-100 text-orange-700 rounded-full flex items-center justify-center text-sm font-medium flex-shrink-0">
                {idx + 1}
              </span>
              <span className="text-gray-700 font-normal leading-relaxed">{step}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Data Sources by Country */}
      {papers && papers.length > 0 && (
        <div className="mt-6 pt-4">
          {(() => {
            const countryStats = getCountryStats(papers)
            const topCountries = countryStats.topCountries.map(([country, count]) => `${country} (${count})`).join(', ')
            return (
              <p className="text-sm text-gray-500">
                Evidence from {countryStats.totalCountries} countries. Top sources: {topCountries}.
              </p>
            )
          })()}
        </div>
      )}
    </div>
  );
}



export default function ResultsPage() {
  const [activeTab, setActiveTab] = useState('summary')
  const [evidenceViewMode, setEvidenceViewMode] = useState<'cards' | 'table'>('table')
  const [projectDocuments, setProjectDocuments] = useState<Record<string, unknown>[]>([])
  const [loadingDocuments, setLoadingDocuments] = useState(false)
  const [documentsError, setDocumentsError] = useState<string | null>(null)
  const [insightsProcessing] = useState(false)
  const [policyProcessing] = useState(false)
  const [briefProcessing] = useState(false)
  // const [lastSearchTime, setLastSearchTime] = useState<number | null>(null)
  const [briefCollapsed, setBriefCollapsed] = useState(false)
  const [insightsCollapsed, setInsightsCollapsed] = useState(false)
  const [policyCollapsed, setPolicyCollapsed] = useState(false)
  
  const { 
    isOpen, 
    setIsOpen, 
    clearMessages, 
    searchResults, 
    searchInProgress, 
    searchCompleted,
    setSearchResults,
    setSearchInProgress,
    setSearchCompleted,
    conversationId,
    setConversationState
  } = useChatbotStore()
  const { fetchWithAuth, getProjectDocuments } = useAPI()
  const { activeProject } = useProjectStore()
  const router = useRouter()
  const urlSearchParams = useSearchParams()
  const query = urlSearchParams.get('query') || ''
  const hasAutoOpenedRef = useRef(false)
  const searchInitiatedRef = useRef<string | null>(null) // Track search key to prevent duplicates
  const [searchError, setSearchError] = useState<string | null>(null)

  // Load project documents when active project changes
  useEffect(() => {
    const loadProjectDocuments = async () => {
      if (!activeProject) {
        setProjectDocuments([])
        // Clear search results when no project is selected
        setSearchResults(null)
        setSearchCompleted(false)
        return
      }

      // Clear cached search results when switching to a project view
      setSearchResults(null)
      setSearchCompleted(false)
      setLoadingDocuments(true)
      setDocumentsError(null)
      
      try {
        const response = await getProjectDocuments(activeProject.id)
        setProjectDocuments(response.documents)
        
        // If project has evidence, set chatbot to chat state
        if (response.documents && response.documents.length > 0) {
          setConversationState('chat')
        }
      } catch (error) {
        console.error('Failed to load project documents:', error)
        setDocumentsError(error instanceof Error ? error.message : 'Failed to load documents')
      } finally {
        setLoadingDocuments(false)
      }
    }

    loadProjectDocuments()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject]) // getProjectDocuments and setters are stable within the scope

  // Reload project documents when a search is completed for the active project
  useEffect(() => {
    const reloadProjectDocuments = async () => {
      if (!activeProject || !searchCompleted || searchInProgress) {
        return
      }

      console.log('Search completed for project, reloading documents...')
      setLoadingDocuments(true)
      
      try {
        const response = await getProjectDocuments(activeProject.id)
        setProjectDocuments(response.documents)
        console.log('Project documents reloaded:', response.documents.length, 'documents')
      } catch (error) {
        console.error('Error reloading project documents after search:', error)
        setDocumentsError(error instanceof Error ? error.message : 'Failed to reload documents')
      } finally {
        setLoadingDocuments(false)
      }
    }

    // Add a small delay to ensure search results are stored in backend
    const timeoutId = setTimeout(reloadProjectDocuments, 1000)
    return () => clearTimeout(timeoutId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchCompleted, activeProject?.id]) // getProjectDocuments and setters are stable within the scope

  // Trigger search if not already completed (for query-based searches)
  useEffect(() => {
    const performSearch = async () => {
      if (!query || searchCompleted || searchInProgress) {
        return
      }
      
      // Create a unique search key to prevent duplicate searches
      const searchKey = `${query}-${conversationId || 'no-conv'}-${activeProject?.id || 'no-project'}`
      
      // Check if we've already initiated this exact search
      if (searchInitiatedRef.current === searchKey) {
        return
      }
      
      // Mark this search as initiated
      searchInitiatedRef.current = searchKey
      setSearchInProgress(true)
      setSearchError(null)
      
      try {
        console.log('Starting search with key:', searchKey)
        const results = await fetchWithAuth('/api/agent/search', {
          method: 'POST',
          body: JSON.stringify({ 
            query,
            conversation_id: conversationId,
            project_id: activeProject?.id
          })
        })
        
        setSearchResults(results)
        setSearchCompleted(true)
        
        // Update conversation state to chat if evidence was found
        if (results.conversation_updated) {
          setConversationState('chat')
        }
      } catch (error) {
        console.error('Search failed:', error)
        setSearchError(error instanceof Error ? error.message : 'Search failed')
        // Reset the search key on error so it can be retried
        searchInitiatedRef.current = null
      } finally {
        setSearchInProgress(false)
      }
    }
    
    performSearch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, searchCompleted, searchInProgress, conversationId, activeProject?.id]) // API functions and setters are stable within scope

  useEffect(() => {
    // Auto-show chatbot when arriving from chat page (only once)
    if (query && !isOpen && !hasAutoOpenedRef.current) {
      hasAutoOpenedRef.current = true
      const timer = setTimeout(() => {
        setIsOpen(true)
      }, 1000) // Small delay to let the page load
      return () => clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, isOpen]) // setIsOpen is stable from Zustand store

  // Simple polling: refresh project data every 5 seconds after search completes
  useEffect(() => {
    const activeProjectId = activeProject?.id
    if (!searchCompleted || !activeProjectId) return
    
    const refreshProject = async () => {
      try {
        const updatedProject = await fetchWithAuth(`projects/${activeProjectId}?t=${Date.now()}`)
        const { updateProject } = useProjectStore.getState()
        updateProject(activeProjectId, updatedProject)
      } catch (error) {
        console.error('Error refreshing project:', error)
      }
    }
    
    // Refresh immediately, then every 5 seconds
    refreshProject()
    const interval = setInterval(refreshProject, 5000)
    
    // Stop after 10 minutes
    const timeout = setTimeout(() => {
      clearInterval(interval)
    }, 600000)
    
    return () => {
      clearInterval(interval)
      clearTimeout(timeout)
    }
  }, [searchCompleted, activeProject?.id, fetchWithAuth])

  // Manual refresh function
  const handleRefreshProject = async () => {
    if (!activeProject) return
    
    try {
      const updatedProject = await fetchWithAuth(`projects/${activeProject.id}?t=${Date.now()}`)
      const { updateProject } = useProjectStore.getState()
      updateProject(activeProject.id, updatedProject)
    } catch (error) {
      console.error('Error manually refreshing project:', error)
    }
  }

  const handleNewSearch = () => {
    // Clear conversation and start fresh
    clearMessages()
    // Reset search initiated ref so new searches can proceed
    searchInitiatedRef.current = null
    router.push('/agent')
  }



  // Use project documents when a project is selected, otherwise fall back to search results
  // But only use cached search results if no project is selected
  const displayResults = activeProject ? {
    // When project is selected, show project documents (even if empty)
    papers: projectDocuments,
    total_found: projectDocuments.length,
    total_screened: projectDocuments.length,
    total_relevant: projectDocuments.filter(doc => {
      const metadata = doc.metadata as { is_relevant?: boolean } | undefined
      return metadata?.is_relevant !== false
    }).length
  } : (searchResults || {
    // Only use cached search results when no project is selected
    papers: [],
    total_found: 0,
    total_screened: 0,
    total_relevant: 0
  })

  // Transform papers/documents for table compatibility
  const transformedPapers: Paper[] = displayResults.papers.map((paper: Record<string, unknown>) => {
    // Extract publication year with better fallback logic
    let publicationYear: number | null = null

    const metadata = (paper.metadata as Record<string, unknown> | undefined) || undefined

    const isValidYear = (y: unknown): y is number => {
      const n = typeof y === 'string' ? parseInt(y, 10) : Number(y)
      return !isNaN(n) && n > 1900 && n <= new Date().getFullYear()
    }

    const yearFromDateString = (dateVal: unknown): number | null => {
      if (!dateVal) return null
      try {
        const s = String(dateVal)
        if (s && s.length >= 4) {
          const yr = parseInt(s.slice(0, 4), 10)
          return isValidYear(yr) ? yr : null
        }
      } catch {}
      return null
    }

    // 1) Prefer explicit metadata.publication_year if present
    if (metadata && isValidYear((metadata as { publication_year?: unknown }).publication_year)) {
      publicationYear = Number((metadata as { publication_year?: unknown }).publication_year)
    }
    // 2) Then top-level publication_year
    else if (isValidYear(paper.publication_year)) {
      publicationYear = Number(paper.publication_year)
    }
    // 3) Then try published_date (from Supabase), publication_date, published_on
    else {
      publicationYear =
        yearFromDateString((paper as { published_date?: unknown }).published_date) ||
        yearFromDateString((paper as { publication_date?: unknown }).publication_date) ||
        yearFromDateString((paper as { published_on?: unknown }).published_on)
    }

    return {
      // Ensure required fields for table component
      id: String(paper.id || `paper-${Math.random()}`),
      title: String(paper.title || 'Untitled'),
      doi: String(paper.doi || ''),
      publication_year: publicationYear || 0, // Use 0 for unknown years instead of current year
      cited_by_count: Number((paper as { cited_by_count?: unknown }).cited_by_count || (metadata && (metadata as { cited_by_count?: unknown }).cited_by_count) || (paper as { citation_count?: unknown }).citation_count || 0),
      authors: Array.isArray((paper as { authors?: unknown }).authors) ? (paper as { authors?: unknown[] }).authors!.map(String) : ((paper as { authors?: unknown }).authors ? [String((paper as { authors?: unknown }).authors!)] : ['Unknown']),
      is_relevant: Boolean(paper.is_relevant !== false), // Default to true if not specified
      // Include other properties that might be present
      abstract: (paper as { abstract?: unknown }).abstract ? String((paper as { abstract?: unknown }).abstract) : undefined,
      venue: (paper as { venue?: unknown }).venue ? String((paper as { venue?: unknown }).venue) : undefined,
      relevance_reason: (paper as { relevance_reason?: unknown }).relevance_reason ? String((paper as { relevance_reason?: unknown }).relevance_reason) : undefined,
      confidence: (paper as { confidence?: unknown }).confidence ? Number((paper as { confidence?: unknown }).confidence) : undefined,
      topics: Array.isArray((paper as { topics?: unknown }).topics) ? (paper as { topics?: unknown[] }).topics!.map(String) : undefined,
      source_country: (paper as { source_country?: unknown }).source_country ? String((paper as { source_country?: unknown }).source_country) : undefined,
      source_type: (paper as { source_type?: unknown }).source_type ? String((paper as { source_type?: unknown }).source_type) : undefined,
      published_on: (paper as { published_on?: unknown }).published_on ? String((paper as { published_on?: unknown }).published_on) : undefined,
      overton_url: (paper as { overton_url?: unknown }).overton_url ? String((paper as { overton_url?: unknown }).overton_url) : undefined,
      top_line: (paper as { top_line?: unknown }).top_line ? String((paper as { top_line?: unknown }).top_line) : undefined
    }
  })

  return (
    <div className="flex-1 flex flex-col">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <div className="flex items-center justify-between">
          <div className="flex flex-col">
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-bold text-slate-900">
                {activeProject ? 'Results' : 'Search Results'}
              </h1>
              {/* {activeProject && (
                <div className="flex items-center gap-2 text-slate-600">
                  <FolderOpen className="h-5 w-5" />
                  <span className="font-medium">{activeProject.name}</span>
                </div>
              )} */}
            </div>
            <div className="flex items-center gap-2">
              {loadingDocuments && (
                <Badge variant="secondary" className="bg-blue-100 text-blue-700">
                  Loading documents...
                </Badge>
              )}
              {documentsError && (
                <Badge variant="secondary" className="bg-red-100 text-red-700">
                  Error loading documents
                </Badge>
              )}
              {searchInProgress && (
                <Badge variant="secondary" className="bg-blue-100 text-blue-700">
                  Searching...
                </Badge>
              )}
              {searchError && (
                <Badge variant="secondary" className="bg-red-100 text-red-700">
                  Search Error
                </Badge>
              )}
              {(searchCompleted || (activeProject && projectDocuments.length > 0)) && (
                <>
                  <Badge variant="secondary" className="bg-green-100 text-green-700">
                    {displayResults.total_relevant} Sources
                  </Badge>
                  {/* <Badge variant="secondary" className="bg-yellow-100 text-yellow-700">
                    {displayResults.total_found} Total Found
                  </Badge> */}
                  {/* <Badge variant="secondary" className="bg-blue-100 text-blue-700">
                    AI Screened
                  </Badge> */}
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* <Button variant="outline" size="sm">
              <Download className="h-4 w-4 mr-2" />
              Export Report
            </Button> */}
            <Button onClick={handleRefreshProject} variant="outline" size="sm">
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            <Button onClick={handleNewSearch} className="bg-blue-600 hover:bg-blue-700">
              <Search className="h-4 w-4 mr-2" />
              New Search
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 bg-slate-50">
        {/* No Project Selected or No Documents */}
        {!activeProject ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center p-8">
              <FolderOpen className="h-16 w-16 text-slate-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">No Project Selected</h3>
              <p className="text-slate-600 mb-6">
                Select a project from the Projects page to view its evidence and documents.
              </p>
              <Button 
                onClick={() => router.push('/agent/projects')}
                className="bg-blue-600 hover:bg-blue-700"
              >
                <FolderOpen className="h-4 w-4 mr-2" />
                Go to Projects
              </Button>
            </div>
          </div>
        ) : projectDocuments.length === 0 && !loadingDocuments ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center p-8">
              <BookOpen className="h-16 w-16 text-slate-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">No Evidence Yet</h3>
              <p className="text-slate-600 mb-6">
                This project doesn&apos;t have any evidence documents yet. Perform searches to add evidence to this project.
              </p>
              <Button 
                onClick={() => router.push('/agent')}
                className="bg-blue-600 hover:bg-blue-700"
              >
                <Search className="h-4 w-4 mr-2" />
                Start Searching
              </Button>
            </div>
          </div>
        ) : (
          <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
          <div className="px-6 pt-4">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="summary" className="flex items-center gap-2">
                <FileText className="h-4 w-4" />
                Summary
              </TabsTrigger>
              <TabsTrigger value="evidence" className="flex items-center gap-2">
                <BookOpen className="h-4 w-4" />
                Evidence
              </TabsTrigger>
              <TabsTrigger value="insights" className="flex items-center gap-2">
                <Lightbulb className="h-4 w-4" />
                Insights
              </TabsTrigger>              
              <TabsTrigger value="assistant" className="flex items-center gap-2">
                <Bot className="h-4 w-4" />
                Assistant
              </TabsTrigger>
            </TabsList>
          </div>

          <div className="flex-1 overflow-auto">
            <TabsContent value="summary" className="p-6 m-0">
              <div className="w-full">
                {/* Executive Brief */}
                <Card className="mb-8">
                  <CardHeader className="relative">
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2">
                        <FileText className="h-5 w-5" />
                        Executive Brief
                      </CardTitle>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setBriefCollapsed(!briefCollapsed)}
                        className="h-8 w-8 p-0"
                      >
                        <ChevronDown className={`h-4 w-4 transition-transform ${briefCollapsed ? 'rotate-180' : ''}`} />
                      </Button>
                    </div>
                  </CardHeader>
                  {!briefCollapsed && (
                    <CardContent>
                                          {activeProject?.executive_brief ? (
                      <ExecutiveBriefDisplay brief={activeProject.executive_brief} papers={transformedPapers} />
                    ) : briefProcessing ? (
                        <div className="text-center py-8">
                          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto mb-4"></div>
                          <h3 className="text-lg font-medium text-gray-600 mb-2">Generating Executive Brief</h3>
                          <p className="text-gray-500 mb-4">
                            Creating comprehensive executive summary combining insights and recommendations...
                          </p>
                          <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 text-sm text-purple-800">
                            <div className="flex items-center gap-2">
                              <div className="w-2 h-2 bg-purple-500 rounded-full animate-pulse"></div>
                              Usually completes after policy recommendations (30-60 seconds)
                            </div>
                          </div>
                        </div>
                      ) : activeProject?.policy_recommendations ? (
                        <div className="text-center py-8">
                          <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-gray-600 mb-2">Executive Brief Ready</h3>
                          <p className="text-gray-500 mb-4">
                            Policy recommendations are available. Executive brief is automatically generated and should appear shortly.
                          </p>
                          <div className="text-sm text-gray-400">
                            If the brief doesn&apos;t appear, it may still be processing in the background.
                          </div>
                        </div>
                      ) : (
                        <div className="text-center py-8">
                          <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-gray-600 mb-2">Analysis Required</h3>
                          <p className="text-gray-500 mb-4">
                            Executive brief is generated after insights and policy recommendations are completed.
                          </p>
                          <div className="text-sm text-gray-400">
                            This provides a comprehensive summary for executive decision-making.
                          </div>
                        </div>
                      )}
                    </CardContent>
                  )}
                </Card>

                {/* Key Insights */}
                <Card>
                  <CardHeader className="relative">
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2">
                        <TrendingUp className="h-5 w-5" />
                        Key Insights
                      </CardTitle>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setInsightsCollapsed(!insightsCollapsed)}
                        className="h-8 w-8 p-0"
                      >
                        <ChevronDown className={`h-4 w-4 transition-transform ${insightsCollapsed ? 'rotate-180' : ''}`} />
                      </Button>
                    </div>
                  </CardHeader>
                  {!insightsCollapsed && (
                    <CardContent>
                      {activeProject?.key_insights ? (
                        <KeyInsightsDisplay insights={activeProject.key_insights} />
                      ) : insightsProcessing ? (
                        <div className="text-center py-8">
                          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                          <h3 className="text-lg font-medium text-gray-600 mb-2">Generating Key Insights</h3>
                          <p className="text-gray-500 mb-4">
                            Our AI is analyzing your evidence to extract key insights and findings...
                          </p>
                          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                            <div className="flex items-center gap-2">
                              <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                              This usually takes 30-60 seconds
                            </div>
                          </div>
                        </div>
                      ) : displayResults.papers.length >= 3 ? (
                        <div className="text-center py-8">
                          <Lightbulb className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-gray-600 mb-2">Ready for Insights</h3>
                          <p className="text-gray-500 mb-4">
                            You have {displayResults.papers.length} pieces of evidence. Insights are automatically generated after search completion.
                          </p>
                          <div className="text-sm text-gray-400">
                            If insights don&apos;t appear automatically, they may still be processing in the background.
                          </div>
                        </div>
                      ) : (
                        <div className="text-center py-8">
                          <Lightbulb className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-gray-600 mb-2">Insufficient Evidence</h3>
                          <p className="text-gray-500 mb-4">
                            You need at least 3 pieces of evidence to generate meaningful insights.
                          </p>
                          <div className="text-sm text-gray-400">
                            Current evidence: {displayResults.papers.length} documents
                          </div>
                        </div>
                      )}
                    </CardContent>
                  )}
                </Card>

                {/* Policy Recommendations */}
                <Card className="mt-8">
                  <CardHeader className="relative">
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2">
                        <TrendingUp className="h-5 w-5" />
                        Policy Recommendations
                      </CardTitle>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setPolicyCollapsed(!policyCollapsed)}
                        className="h-8 w-8 p-0"
                      >
                        <ChevronDown className={`h-4 w-4 transition-transform ${policyCollapsed ? 'rotate-180' : ''}`} />
                      </Button>
                    </div>
                  </CardHeader>
                  {!policyCollapsed && (
                    <CardContent>
                      {activeProject?.policy_recommendations ? (
                        <PolicyRecommendationsDisplay recommendations={activeProject.policy_recommendations} />
                      ) : policyProcessing ? (
                        <div className="text-center py-8">
                          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto mb-4"></div>
                          <h3 className="text-lg font-medium text-gray-600 mb-2">Generating Policy Recommendations</h3>
                          <p className="text-gray-500 mb-4">
                            Analyzing evidence to develop actionable policy recommendations...
                          </p>
                          <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-800">
                            <div className="flex items-center gap-2">
                              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                              Usually completes after insights generation (1-2 minutes)
                            </div>
                          </div>
                        </div>
                      ) : activeProject?.key_insights ? (
                        <div className="text-center py-8">
                          <TrendingUp className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-gray-600 mb-2">Policy Recommendations Ready</h3>
                          <p className="text-gray-500 mb-4">
                            Insights are available. Policy recommendations are automatically generated and should appear shortly.
                          </p>
                          <div className="text-sm text-gray-400">
                            If recommendations don&apos;t appear, they may still be processing in the background.
                          </div>
                        </div>
                      ) : (
                        <div className="text-center py-8">
                          <TrendingUp className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                          <h3 className="text-lg font-medium text-gray-600 mb-2">Insights Required</h3>
                          <p className="text-gray-500 mb-4">
                            Policy recommendations are generated after key insights are extracted from your evidence.
                          </p>
                          <div className="text-sm text-gray-400">
                            Check above for insights generation progress.
                          </div>
                        </div>
                      )}
                    </CardContent>
                  )}
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="evidence" className="p-6 m-0">
              <div className="w-full">
                {/* View Toggle Header */}
                {((activeProject && !loadingDocuments) || (searchCompleted)) && displayResults.papers.length > 0 && (
                  <div className="flex justify-end items-center mb-6">
                    {/* <h3 className="text-lg font-medium text-slate-900">Evidence ({displayResults.papers.length} documents)</h3> */}
                    <ViewToggle currentView={evidenceViewMode} onViewChange={setEvidenceViewMode} />
                  </div>
                )}

                {searchInProgress && (
                  <div className="flex items-center justify-center py-12">
                    <div className="text-center">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
                      <p className="text-slate-600">Searching and screening evidence...</p>
                    </div>
                  </div>
                )}
                
                {searchError && (
                  <div className="flex items-center justify-center py-12">
                    <div className="text-center">
                      <p className="text-red-600 mb-2">Error searching for evidence</p>
                      <p className="text-slate-600 text-sm">{searchError}</p>
                    </div>
                  </div>
                )}
                
                {searchCompleted && displayResults.papers.length === 0 && (
                  <div className="flex items-center justify-center py-12">
                    <div className="text-center">
                      <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                      <h3 className="text-lg font-medium text-slate-900 mb-2">No relevant evidence found</h3>
                      <p className="text-slate-600">Try refining your search query or adjusting the scope</p>
                    </div>
                  </div>
                )}
                
                {!searchInProgress && !searchCompleted && !loadingDocuments && activeProject && displayResults.papers.length === 0 && (
                  <div className="flex items-center justify-center py-12">
                    <div className="text-center">
                      <BookOpen className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                      <h3 className="text-lg font-medium text-slate-900 mb-2">Ready to gather evidence</h3>
                      <p className="text-slate-600 mb-6">This project is ready for evidence collection. Start a search to add documents.</p>
                      <Button 
                        onClick={() => router.push('/agent')}
                        className="bg-blue-600 hover:bg-blue-700"
                      >
                        <Search className="h-4 w-4 mr-2" />
                        Start Searching
                      </Button>
                    </div>
                  </div>
                )}
                
                {((activeProject && !loadingDocuments) || (searchCompleted)) && displayResults.papers.length > 0 && (
                  <>
                    {/* Table View */}
                    {evidenceViewMode === 'table' && (
                      <PapersTable papers={transformedPapers} />
                    )}

                    {/* Cards View */}
                    {evidenceViewMode === 'cards' && (
                      <div className="space-y-6">
                        {transformedPapers.map((paper: Paper, index: number) => (
                          <Card key={paper.id || index} className="border-slate-200">
                            <CardContent className="p-6">
                              <div className="flex justify-between items-start mb-4">
                                <div className="flex-1">
                                  <h3 className="font-semibold text-lg text-slate-900 mb-2">
                                    {paper.title || 'Untitled'}
                                  </h3>
                                  <p className="text-slate-600 text-sm mb-2">
                                    {Array.isArray(paper.authors) ? paper.authors.join(', ') : 'Unknown authors'} 
                                    {paper.publication_year && ` • ${paper.publication_year}`}
                                  </p>
                                  <div className="flex items-center gap-2 mb-2">
                                    <Badge variant="outline" className="text-xs">
                                      Policy Document
                                    </Badge>
                                    {paper.source_country && (
                                      <Badge variant="outline" className="text-xs">
                                        {paper.source_country}
                                      </Badge>
                                    )}
                                  </div>
                                </div>
                                <div className="text-right">
                                  <div className="text-sm font-medium text-slate-900">
                                    {Math.round((paper.confidence || 0) * 100)}% Confidence
                                  </div>
                                  <Progress value={(paper.confidence || 0) * 100} className="w-20 mt-1" />
                                </div>
                              </div>
                              
                              {paper.top_line && (
                                <div className="bg-slate-50 rounded-lg p-4 mb-4">
                                  <h4 className="font-medium text-slate-900 mb-2">Key Finding</h4>
                                  <p className="text-slate-700 text-sm leading-relaxed">
                                    {paper.top_line}
                                  </p>
                                </div>
                              )}

                              {paper.relevance_reason && (
                                <div className="mb-4">
                                  <h4 className="font-medium text-slate-900 mb-2">Relevance</h4>
                                  <p className="text-slate-600 text-sm">
                                    {paper.relevance_reason}
                                  </p>
                                </div>
                              )}

                              {paper.abstract && (
                                <div className="mb-4">
                                  <h4 className="font-medium text-slate-900 mb-2">Abstract</h4>
                                  <p className="text-slate-600 text-sm line-clamp-3">
                                    {paper.abstract}
                                  </p>
                                </div>
                              )}

                              {(paper.doi || paper.overton_url || paper.id) && (
                                <div className="flex items-center gap-2 pt-2 border-t border-slate-200">
                                  <span className="text-slate-500 text-xs">Source:</span>
                                  {paper.doi && (
                                    <a 
                                      href={paper.doi.startsWith('http') ? paper.doi : `https://doi.org/${paper.doi}`} 
                                      target="_blank" 
                                      rel="noopener noreferrer"
                                      className="text-blue-600 hover:text-blue-800 text-xs underline"
                                    >
                                      DOI Link
                                    </a>
                                  )}
                                  {!paper.doi && paper.overton_url && (
                                    <a 
                                      href={paper.overton_url} 
                                      target="_blank" 
                                      rel="noopener noreferrer"
                                      className="text-blue-600 hover:text-blue-800 text-xs underline"
                                    >
                                      View Document
                                    </a>
                                  )}
                                  {!paper.doi && !paper.overton_url && paper.id && (
                                    <span className="text-slate-500 text-xs">ID: {paper.id}</span>
                                  )}
                                </div>
                              )}
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            </TabsContent>


            <TabsContent value="assistant" className="m-0 h-[600px]">
              <ChatInterface 
                autoFocus={true}
                placeholder="Continue refining your research question or ask about the evidence..."
                className="h-full"
              />
            </TabsContent>

            <TabsContent value="insights" className="p-6 m-0">
              <div className="space-y-6">
                {loadingDocuments ? (
                  <div className="flex items-center justify-center h-96">
                    <div className="text-center">
                      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                      <h3 className="text-lg font-medium text-gray-600 mb-2">Loading Analytics</h3>
                      <p className="text-gray-500">Preparing your data for analysis...</p>
                    </div>
                  </div>
                ) : documentsError ? (
                  <div className="flex items-center justify-center h-96">
                    <div className="text-center">
                      <AlertTriangle className="h-12 w-12 text-red-400 mx-auto mb-4" />
                      <h3 className="text-lg font-medium text-gray-900 mb-2">Error Loading Data</h3>
                      <p className="text-gray-600">Failed to load project documents for analytics</p>
                    </div>
                  </div>
                ) : displayResults.papers.length > 0 ? (
                  <SimpleAnalytics papers={transformedPapers} />
                ) : (
                  <div className="flex items-center justify-center h-96">
                    <div className="text-center">
                      <Lightbulb className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                      <h3 className="text-lg font-medium text-slate-900 mb-2">No Data Available</h3>
                      <p className="text-slate-600">Add some evidence documents to see analytics</p>
                    </div>
                  </div>
                )}
              </div>
            </TabsContent>
          </div>
        </Tabs>
        )}
      </div>

      {/* Floating Chatbot Widget */}
      <ChatbotWidget 
        isOpen={isOpen}
        onToggle={() => setIsOpen(!isOpen)}
        researchQuestion={query}
      />
    </div>
  )
}
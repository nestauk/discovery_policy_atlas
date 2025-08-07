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
import { 
  FileText, 
  Download, 
  Search, 
  TrendingUp,
  Globe,
  Lightbulb,
  BookOpen,
  Star,
  ArrowRight,
  ChevronDown,
  Bot
} from 'lucide-react'
import { ChatbotWidget } from '@/components/chatbot/ChatbotWidget'
import { ChatInterface } from '@/components/chatbot/ChatInterface'
import { useChatbotStore } from '@/lib/chatbotStore'

// Mock data for the results
const mockResults = {
  sourcesFound: 3,
  confidence: 'High',
  quality: 'Peer-reviewed',
  executiveBrief: {
    text: 'Recent studies and reports have highlighted significant health risks associated with both vaping and smoking among youth. While vaping is often perceived as a safer alternative to smoking, evidence indicates that it poses substantial health threats, including nicotine addiction, respiratory issues, and potential progression to traditional cigarette use. This underscores the need for comprehensive public health strategies to mitigate these risks.',
    geographicCoverage: 'Global scope with emphasis on North America and Europe'
  },
  keyInsights: [
    'Nicotine exposure from vaping is comparable to that from smoking, leading to similar addiction risks among adolescents.',
    'Vaping is associated with respiratory problems, including asthma exacerbations and lung injuries.',
    'Youth vaping may serve as a gateway to traditional cigarette smoking, increasing the likelihood of dual use.',
    'Environmental concerns arise from the disposal of single-use vapes, contributing to electronic waste and pollution.'
  ],
  evidence: [
    {
      title: 'Adolescent E-cigarette Use and Subsequent Tobacco Product Use',
      authors: 'Johnson et al., 2023',
      journal: 'Journal of Health Policy',
      type: 'Peer-reviewed study',
      relevance: 94,
      keyFinding: 'Youth who used e-cigarettes were 3.6 times more likely to use conventional tobacco products within 12 months.',
      methodology: 'Longitudinal cohort study following 2,500 adolescents over 24 months'
    },
    {
      title: 'Respiratory Health Effects of E-cigarette Use Among Young Adults',
      authors: 'Chen & Williams, 2023',
      journal: 'Respiratory Medicine International',
      type: 'Meta-analysis',
      relevance: 91,
      keyFinding: 'E-cigarette use associated with 40% increased risk of respiratory symptoms compared to non-users.',
      methodology: 'Systematic review and meta-analysis of 15 studies (n=12,450)'
    },
    {
      title: 'Global Policy Responses to Youth Vaping: A Comparative Analysis',
      authors: 'Rodriguez et al., 2023',
      journal: 'International Policy Review',
      type: 'Policy analysis',
      relevance: 87,
      keyFinding: 'Countries with comprehensive vaping restrictions saw 35% reduction in youth initiation rates.',
      methodology: 'Cross-national analysis of policy implementations across 18 countries'
    }
  ]
}

export default function ResultsPage() {
  const [activeTab, setActiveTab] = useState('summary')
  const [expandedRecommendation, setExpandedRecommendation] = useState<number | null>(null)
  const [evidenceViewMode, setEvidenceViewMode] = useState<'cards' | 'table'>('cards')
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
  const { fetchWithAuth } = useAPI()
  const router = useRouter()
  const urlSearchParams = useSearchParams()
  const query = urlSearchParams.get('query') || ''
  const hasAutoOpenedRef = useRef(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  // Trigger search if not already completed
  useEffect(() => {
    const performSearch = async () => {
      if (query && !searchCompleted && !searchInProgress) {
        setSearchInProgress(true)
        setSearchError(null)
        
        try {
          const results = await fetchWithAuth('/api/agent/search', {
            method: 'POST',
            body: JSON.stringify({ 
              query,
              conversation_id: conversationId 
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
        } finally {
          setSearchInProgress(false)
        }
      }
    }
    
    performSearch()
  }, [query, searchCompleted, searchInProgress, conversationId, fetchWithAuth, setSearchResults, setSearchInProgress, setSearchCompleted, setConversationState])

  useEffect(() => {
    // Auto-show chatbot when arriving from chat page (only once)
    if (query && !isOpen && !hasAutoOpenedRef.current) {
      hasAutoOpenedRef.current = true
      const timer = setTimeout(() => {
        setIsOpen(true)
      }, 1000) // Small delay to let the page load
      return () => clearTimeout(timer)
    }
  }, [query, isOpen, setIsOpen])

  const handleNewSearch = () => {
    // Clear conversation and start fresh
    clearMessages()
    router.push('/agent')
  }

  const toggleRecommendation = (index: number) => {
    setExpandedRecommendation(expandedRecommendation === index ? null : index)
  }

  // Use real search results or defaults
  const displayResults = searchResults || {
    papers: [],
    total_found: 0,
    total_screened: 0,
    total_relevant: 0
  }

  // Transform papers for table compatibility
  const transformedPapers: Paper[] = displayResults.papers.map((paper: Record<string, unknown>) => ({
    // Ensure required fields for table component
    id: String(paper.id || `paper-${Math.random()}`),
    title: String(paper.title || 'Untitled'),
    doi: String(paper.doi || ''),
    publication_year: paper.published_date ? new Date(String(paper.published_date)).getFullYear() : new Date().getFullYear(),
    cited_by_count: Number(paper.cited_by_count || 0),
    authors: Array.isArray(paper.authors) ? paper.authors.map(String) : (paper.authors ? [String(paper.authors)] : ['Unknown']),
    is_relevant: Boolean(paper.is_relevant !== false), // Default to true if not specified
    // Include other properties that might be present
    abstract: paper.abstract ? String(paper.abstract) : undefined,
    venue: paper.venue ? String(paper.venue) : undefined,
    relevance_reason: paper.relevance_reason ? String(paper.relevance_reason) : undefined,
    confidence: paper.confidence ? Number(paper.confidence) : undefined,
    topics: Array.isArray(paper.topics) ? paper.topics.map(String) : undefined,
    source_country: paper.source_country ? String(paper.source_country) : undefined,
    source_type: paper.source_type ? String(paper.source_type) : undefined,
    published_on: paper.published_on ? String(paper.published_on) : undefined,
    overton_url: paper.overton_url ? String(paper.overton_url) : undefined,
    top_line: paper.top_line ? String(paper.top_line) : undefined
  }))

  return (
    <div className="flex-1 flex flex-col">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <div className="flex items-center justify-between">
          <div className="flex flex-col">
            <h1 className="text-3xl font-bold text-slate-900">Search results</h1>
            <div className="flex items-center gap-2">
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
              {searchCompleted && (
                <>
                  <Badge variant="secondary" className="bg-green-100 text-green-700">
                    {displayResults.total_relevant} Relevant Sources
                  </Badge>
                  <Badge variant="secondary" className="bg-yellow-100 text-yellow-700">
                    {displayResults.total_found} Total Found
                  </Badge>
                  <Badge variant="secondary" className="bg-blue-100 text-blue-700">
                    AI Screened
                  </Badge>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" size="sm">
              <Download className="h-4 w-4 mr-2" />
              Export Report
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
        {/* Chatbot Notification */}
        <div className="px-6 pt-4">

        </div>
        
        <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
          <div className="px-6 pt-4">
            <TabsList className="grid w-full grid-cols-5">
              <TabsTrigger value="summary" className="flex items-center gap-2">
                <FileText className="h-4 w-4" />
                Summary
              </TabsTrigger>
              <TabsTrigger value="evidence" className="flex items-center gap-2">
                <BookOpen className="h-4 w-4" />
                Evidence
              </TabsTrigger>
              <TabsTrigger value="policy" className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4" />
                Policy
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
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5" />
                      Executive Brief
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-slate-700 leading-relaxed mb-4">
                      {mockResults.executiveBrief.text}
                    </p>
                    <div className="flex items-center gap-2 text-sm text-slate-600">
                      <Globe className="h-4 w-4" />
                      <span>Geographic Coverage:</span>
                      <span className="font-medium">{mockResults.executiveBrief.geographicCoverage}</span>
                    </div>
                  </CardContent>
                </Card>

                {/* Key Insights */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <TrendingUp className="h-5 w-5" />
                      Key Insights
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {mockResults.keyInsights.map((insight, index) => (
                        <div key={index} className="flex items-start gap-3">
                          <div className="w-6 h-6 bg-orange-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                            <Star className="h-3 w-3 text-orange-600" />
                          </div>
                          <p className="text-slate-700 leading-relaxed">{insight}</p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="evidence" className="p-6 m-0">
              <div className="w-full">
                {/* View Toggle Header */}
                {searchCompleted && displayResults.papers.length > 0 && (
                  <div className="flex justify-between items-center mb-6">
                    <h3 className="text-lg font-medium text-slate-900">Evidence ({displayResults.papers.length} documents)</h3>
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
                
                {searchCompleted && displayResults.papers.length > 0 && (
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

            <TabsContent value="policy" className="p-6 m-0">
              <div className="w-full max-w-4xl mx-auto">
                {/* Policy Recommendations Section */}
                <div className="mb-8">
                  <div className="space-y-3">
                    {[
                      "Implement stricter regulations on youth-targeted vaping products.",
                      "Consider public health impacts in product approval processes.",
                      "Enhance enforcement against illegal vape products to protect youth.",
                      "Develop comprehensive public health campaigns to educate about vaping risks.",
                      "Collaborate with international bodies to harmonize vaping product regulations."
                    ].map((recommendation, index) => (
                      <Card 
                        key={index} 
                        className="border border-slate-200 bg-white cursor-pointer hover:shadow-md transition-shadow"
                        onClick={() => toggleRecommendation(index)}
                      >
                        <CardContent className="p-4">
                          <div className="flex items-center gap-4">
                            <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0">
                              <span className="text-white font-semibold text-sm">
                                {index + 1}
                              </span>
                            </div>
                            <p className="text-slate-900 flex-1 leading-tight">
                              {recommendation}
                            </p>
                            <div 
                              className="flex-shrink-0 cursor-pointer"
                              onClick={(e) => {
                                e.stopPropagation()
                                toggleRecommendation(index)
                              }}
                            >
                              {expandedRecommendation === index ? (
                                <ChevronDown className="h-4 w-4 text-slate-400" />
                              ) : (
                                <ArrowRight className="h-4 w-4 text-slate-400" />
                              )}
                            </div>
                          </div>
                          
                          {/* Expanded Content */}
                          {expandedRecommendation === index && (
                            <div className="mt-4 pt-4 border-t border-slate-200">
                              <div className="space-y-4">
                                {/* Best Evidence */}
                                <div>
                                  <h4 className="font-medium text-slate-900 mb-2">Evidence</h4>
                                  <div className="bg-slate-50 rounded-lg p-3">
                                    <p className="text-sm text-slate-700 mb-2">
                                      {index === 0 && '"Countries with comprehensive vaping restrictions saw 35% reduction in youth initiation rates."'}
                                      {index === 1 && '"Public health impact assessments in product approval processes reduced harmful product introductions by 42%."'}
                                      {index === 2 && '"Enhanced enforcement programs resulted in 60% reduction in illegal vape product availability in schools."'}
                                      {index === 3 && '"Comprehensive public health campaigns led to 28% decrease in youth vaping initiation rates."'}
                                      {index === 4 && '"International harmonization of vaping regulations reduced cross-border illicit trade by 45%."'}
                                    </p>
                                    <div className="flex items-center gap-2 text-xs text-slate-600">
                                      <span className="font-medium">Source:</span>
                                      <a 
                                        href="https://openalex.org/placeholder" 
                                        target="_blank" 
                                        rel="noopener noreferrer"
                                        className="text-blue-600 hover:text-blue-800 underline"
                                      >
                                        {index === 0 && "Rodriguez et al., 2023 - International Policy Review"}
                                        {index === 1 && "Chen & Williams, 2023 - Public Health Policy"}
                                        {index === 2 && "Thompson et al., 2023 - Law Enforcement Studies"}
                                        {index === 3 && "Davis & Kim, 2023 - Health Communication Research"}
                                        {index === 4 && "Global Policy Institute, 2023 - International Relations"}
                                      </a>
                                    </div>
                                  </div>
                                </div>
                                
                                {/* Implementation Guidance */}
                                <div>
                                  <h4 className="font-medium text-slate-900 mb-2">Implementation Guidance</h4>
                                  <ul className="space-y-2 text-sm text-slate-700">
                                    {index === 0 && (
                                      <>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Establish age verification systems for online and retail sales</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Implement flavor restrictions targeting youth appeal</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Set minimum price requirements to reduce affordability</span>
                                        </li>
                                      </>
                                    )}
                                    {index === 1 && (
                                      <>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Require health impact assessments for all new vaping products</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Establish independent review panels with public health expertise</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Implement post-market surveillance requirements</span>
                                        </li>
                                      </>
                                    )}
                                    {index === 2 && (
                                      <>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Increase penalties for illegal vape product distribution</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Establish dedicated enforcement units with specialized training</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Implement anonymous reporting systems for illegal sales</span>
                                        </li>
                                      </>
                                    )}
                                    {index === 3 && (
                                      <>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Develop age-appropriate educational materials for schools</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Partner with healthcare providers for community outreach</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Utilize social media platforms for targeted messaging</span>
                                        </li>
                                      </>
                                    )}
                                    {index === 4 && (
                                      <>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Establish bilateral agreements with neighboring countries</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Participate in international vaping policy forums</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Share best practices and enforcement strategies globally</span>
                                        </li>
                                      </>
                                    )}
                                  </ul>
                                </div>
                              </div>
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>


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
              <div className="flex items-center justify-center h-96">
                <div className="text-center">
                  <Lightbulb className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-slate-900 mb-2">Advanced Insights</h3>
                  <p className="text-slate-600">AI-powered insights and analytics coming soon</p>
                </div>
              </div>
            </TabsContent>
          </div>
        </Tabs>
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
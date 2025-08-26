'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { useAPI } from '@/lib/api'
import { 
  FileText, 
  BookOpen, 
  Play,
  Loader2,
  CheckCircle,
  Clock
} from 'lucide-react'

interface AnalysisRun {
  run_id: string
  has_references: boolean
  has_extractions: boolean
  created_at: string | null
}

interface AnalysisResult {
  run_id: string
  total_references: number
  relevant_references: number | null
  references_csv_path: string
  extractions_json_path: string | null
}

interface Reference {
  doc_id: string
  source: string
  title: string
  abstract_or_summary: string | null
  year: number | null
  authors: string[] | string | null
  is_relevant: boolean | null
  relevance_confidence: number | null
  relevance_reason: string | null
  top_line: string | null
  document_type: string | null
  acquisition_status: string | null
  extraction_status: string | null
}

interface Extraction {
  paper_id: string
  issues: Array<{
    idx: number
    label: string
    explanation: string
    supporting_quote: string
  }>
  interventions: Array<{
    idx: number
    name: string
    type: string
    description: string
    study_type: string
    country: string
    population_intervened: string
    sample_size: string | null
    supporting_quote: string
  }>
  results: Array<{
    intervention_idx: number
    outcome_variable: string
    effect_direction: string
    effect_size: string
    result_text: string
    supporting_quote: string
  }>
  conclusion: {
    top_line_summary: string
    detailed_explanation: string
    supporting_quote: string
  }
}

export default function TestAnalysisPage() {
  const [query, setQuery] = useState('')
  const [sources, setSources] = useState(['openalex', 'overton'])
  const [limit, setLimit] = useState(50)
  const [relevanceEnabled, setRelevanceEnabled] = useState(true)
  const [useAbstractsOnly, setUseAbstractsOnly] = useState(false)
  const [mode, setMode] = useState('semantic')
  const [booleanQuery, setBooleanQuery] = useState('')
  
  const [isRunning, setIsRunning] = useState(false)
  const [currentRun, setCurrentRun] = useState<AnalysisResult | null>(null)
  const [availableRuns, setAvailableRuns] = useState<AnalysisRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  
  const [references, setReferences] = useState<Reference[]>([])
  const [extractions, setExtractions] = useState<Extraction[]>([])
  const [loadingData, setLoadingData] = useState(false)
  
  const { fetchWithAuth } = useAPI()

  // Load available runs on component mount
  useEffect(() => {
    loadAvailableRuns()
  }, [])

  const loadAvailableRuns = async () => {
    try {
      const response = await fetchWithAuth('/api/analysis/runs')
      setAvailableRuns(response.runs || [])
    } catch {
      console.error('Failed to load analysis runs')
    }
  }

  const runAnalysis = async () => {
    if (!query.trim()) {
      alert('Please enter a query')
      return
    }

    setIsRunning(true)
    setCurrentRun(null)
    
    try {
      const response = await fetchWithAuth('/api/analysis/run', {
        method: 'POST',
        body: JSON.stringify({
          query: query.trim(),
          sources,
          limit,
          relevance_enabled: relevanceEnabled,
          use_abstracts_only: useAbstractsOnly,
          mode,
          boolean_query: booleanQuery || undefined,
        })
      })
      
      setCurrentRun(response)
      setSelectedRunId(response.run_id)
      
      // Reload available runs
      await loadAvailableRuns()
      
    } catch (error) {
      console.error('Analysis failed:', error)
      alert('Analysis failed. Please check the console for details.')
    } finally {
      setIsRunning(false)
    }
  }

  const loadRunData = async (runId: string) => {
    setLoadingData(true)
    setSelectedRunId(runId)
    
    try {
      // Load references
      const refResponse = await fetchWithAuth(`/api/analysis/${runId}/references`)
      setReferences(refResponse.references || [])
      
      // Load extractions if available
      try {
        const extResponse = await fetchWithAuth(`/api/analysis/${runId}/extractions`)
        setExtractions(extResponse.extractions || [])
      } catch (error) {
        console.log('No extractions available for this run')
        setExtractions([])
      }
      
    } catch (error) {
      console.error('Failed to load run data:', error)
      alert('Failed to load run data')
    } finally {
      setLoadingData(false)
    }
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Unknown'
    try {
      return new Date(dateString).toLocaleString()
    } catch {
      return dateString
    }
  }

  return (
    <div className="flex-1 flex flex-col">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Test Analysis Service</h1>
            <p className="text-slate-600 mt-2">
              Test the deterministic analysis pipeline with various configurations
            </p>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 bg-slate-50 p-6">
        <div className="max-w-6xl mx-auto space-y-6">
          
          {/* Analysis Configuration Form */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Play className="h-5 w-5" />
                Analysis Configuration
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="query">Query</Label>
                  <Input
                    id="query"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Enter your research question..."
                    className="mt-1"
                  />
                </div>
                
                <div>
                  <Label htmlFor="limit">Limit</Label>
                  <Input
                    id="limit"
                    type="number"
                    value={limit}
                    onChange={(e) => setLimit(parseInt(e.target.value) || 50)}
                    min="1"
                    max="1000"
                    className="mt-1"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Sources</Label>
                  <div className="flex gap-2 mt-1">
                    {['openalex', 'overton'].map((source) => (
                      <Button
                        key={source}
                        variant={sources.includes(source) ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => {
                          if (sources.includes(source)) {
                            setSources(sources.filter(s => s !== source))
                          } else {
                            setSources([...sources, source])
                          }
                        }}
                      >
                        {source}
                      </Button>
                    ))}
                  </div>
                </div>
                
                <div>
                  <Label>Mode</Label>
                  <div className="flex gap-2 mt-1">
                    {['semantic', 'boolean'].map((m) => (
                      <Button
                        key={m}
                        variant={mode === m ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setMode(m)}
                      >
                        {m}
                      </Button>
                    ))}
                  </div>
                </div>
              </div>

              {mode === 'boolean' && (
                <div>
                  <Label htmlFor="booleanQuery">Boolean Query</Label>
                  <Input
                    id="booleanQuery"
                    value={booleanQuery}
                    onChange={(e) => setBooleanQuery(e.target.value)}
                    placeholder="Enter boolean query (e.g., 'energy AND efficiency')"
                    className="mt-1"
                  />
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="relevance"
                    checked={relevanceEnabled}
                    onChange={(e) => setRelevanceEnabled(e.target.checked)}
                  />
                  <Label htmlFor="relevance">Enable Relevance</Label>
                </div>
                
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="abstracts"
                    checked={useAbstractsOnly}
                    onChange={(e) => setUseAbstractsOnly(e.target.checked)}
                  />
                  <Label htmlFor="abstracts">Abstracts Only</Label>
                </div>
              </div>

              <Button 
                onClick={runAnalysis} 
                disabled={isRunning || !query.trim()}
                className="w-full"
              >
                {isRunning ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Running Analysis...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-2" />
                    Run Analysis
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Current Run Status */}
          {currentRun && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CheckCircle className="h-5 w-5 text-green-600" />
                  Analysis Complete
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-blue-600">{currentRun.total_references}</div>
                    <div className="text-sm text-gray-600">Total References</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-green-600">
                      {currentRun.relevant_references || currentRun.total_references}
                    </div>
                    <div className="text-sm text-gray-600">Relevant References</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-purple-600">{currentRun.run_id}</div>
                    <div className="text-sm text-gray-600">Run ID</div>
                  </div>
                </div>
                <Button 
                  onClick={() => loadRunData(currentRun.run_id)}
                  className="mt-4"
                >
                  <FileText className="h-4 w-4 mr-2" />
                  View Results
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Available Runs */}
          {availableRuns.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Clock className="h-5 w-5" />
                  Available Analysis Runs
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {availableRuns.map((run) => (
                    <div 
                      key={run.run_id}
                      className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer hover:bg-gray-50 ${
                        selectedRunId === run.run_id ? 'border-blue-500 bg-blue-50' : 'border-gray-200'
                      }`}
                      onClick={() => loadRunData(run.run_id)}
                    >
                      <div className="flex items-center gap-3">
                        <div className="text-sm font-mono text-gray-600">{run.run_id}</div>
                        <div className="flex items-center gap-2">
                          {run.has_references && (
                            <Badge variant="secondary" className="bg-green-100 text-green-700">
                              <FileText className="h-3 w-3 mr-1" />
                              References
                            </Badge>
                          )}
                          {run.has_extractions && (
                            <Badge variant="secondary" className="bg-blue-100 text-blue-700">
                              <BookOpen className="h-3 w-3 mr-1" />
                              Extractions
                            </Badge>
                          )}
                        </div>
                      </div>
                      <div className="text-sm text-gray-500">
                        {formatDate(run.created_at)}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Results Display */}
          {selectedRunId && (references.length > 0 || extractions.length > 0) && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  Analysis Results - Run {selectedRunId}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Tabs defaultValue="summary" className="w-full">
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="summary">Summary</TabsTrigger>
                    <TabsTrigger value="evidence">Evidence</TabsTrigger>
                  </TabsList>
                  
                  <TabsContent value="summary" className="mt-6">
                    {loadingData ? (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 className="h-6 w-6 animate-spin mr-2" />
                        Loading extractions...
                      </div>
                    ) : extractions.length > 0 ? (
                      <div className="space-y-6">
                        {extractions.map((extraction, index) => (
                          <Card key={`${extraction.paper_id}-${index}`} className="border-slate-200">
                            <CardHeader>
                              <CardTitle className="text-lg">
                                Paper {index + 1}: {extraction.paper_id}
                              </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                              {/* Issues */}
                              <div>
                                <h4 className="font-semibold text-slate-900 mb-2">Key Issues</h4>
                                <div className="space-y-2">
                                  {extraction.issues.map((issue) => (
                                    <div key={issue.idx} className="bg-red-50 border-l-4 border-red-200 p-3 rounded">
                                      <h5 className="font-medium text-red-900">{issue.label}</h5>
                                      <p className="text-red-700 text-sm mt-1">{issue.explanation}</p>
                                      {issue.supporting_quote && (
                                        <blockquote className="text-red-600 text-xs mt-2 italic">
                                          "{issue.supporting_quote}"
                                        </blockquote>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>

                              {/* Interventions */}
                              <div>
                                <h4 className="font-semibold text-slate-900 mb-2">Interventions</h4>
                                <div className="space-y-2">
                                  {extraction.interventions.map((intervention) => (
                                    <div key={intervention.idx} className="bg-blue-50 border-l-4 border-blue-200 p-3 rounded">
                                      <h5 className="font-medium text-blue-900">{intervention.name}</h5>
                                      <p className="text-blue-700 text-sm mt-1">{intervention.description}</p>
                                      <div className="flex gap-2 mt-2">
                                        <Badge variant="outline" className="text-xs">
                                          {intervention.type}
                                        </Badge>
                                        <Badge variant="outline" className="text-xs">
                                          {intervention.country}
                                        </Badge>
                                      </div>
                                      {intervention.supporting_quote && (
                                        <blockquote className="text-blue-600 text-xs mt-2 italic">
                                          "{intervention.supporting_quote}"
                                        </blockquote>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>

                              {/* Results */}
                              <div>
                                <h4 className="font-semibold text-slate-900 mb-2">Results</h4>
                                <div className="space-y-2">
                                  {extraction.results.map((result, idx) => (
                                    <div key={idx} className="bg-green-50 border-l-4 border-green-200 p-3 rounded">
                                      <div className="flex items-center gap-2 mb-1">
                                        <span className="font-medium text-green-900">
                                          {result.outcome_variable}
                                        </span>
                                        <Badge variant="outline" className="text-xs">
                                          {result.effect_direction}
                                        </Badge>
                                      </div>
                                      <p className="text-green-700 text-sm">{result.result_text}</p>
                                      {result.supporting_quote && (
                                        <blockquote className="text-green-600 text-xs mt-2 italic">
                                          "{result.supporting_quote}"
                                        </blockquote>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>

                              {/* Conclusion */}
                              <div>
                                <h4 className="font-semibold text-slate-900 mb-2">Conclusion</h4>
                                <div className="bg-purple-50 border-l-4 border-purple-200 p-3 rounded">
                                  <h5 className="font-medium text-purple-900">{extraction.conclusion.top_line_summary}</h5>
                                  <p className="text-purple-700 text-sm mt-1">{extraction.conclusion.detailed_explanation}</p>
                                  {extraction.conclusion.supporting_quote && (
                                    <blockquote className="text-purple-600 text-xs mt-2 italic">
                                      "{extraction.conclusion.supporting_quote}"
                                    </blockquote>
                                  )}
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-8 text-gray-500">
                        No extractions available for this run
                      </div>
                    )}
                  </TabsContent>
                  
                  <TabsContent value="evidence" className="mt-6">
                    {loadingData ? (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 className="h-6 w-6 animate-spin mr-2" />
                        Loading references...
                      </div>
                    ) : references.length > 0 ? (
                      <div className="space-y-4">
                        <div className="flex justify-between items-center">
                          <h3 className="text-lg font-medium text-slate-900">
                            References ({references.length})
                          </h3>
                        </div>
                        
                        <div className="space-y-3">
                          {references.map((ref, index) => (
                            <Card key={ref.doc_id} className="border-slate-200">
                              <CardContent className="p-4">
                                <div className="flex justify-between items-start mb-2">
                                  <div className="flex-1">
                                    <h4 className="font-semibold text-slate-900 mb-1">
                                      {ref.title || 'Untitled'}
                                    </h4>
                                    <p className="text-slate-600 text-sm mb-2">
                                      {Array.isArray(ref.authors) ? ref.authors.join(', ') : 
                                       typeof ref.authors === 'string' ? ref.authors.replace(/[\[\]']/g, '') : 
                                       'Unknown authors'} 
                                      {ref.year && ` • ${ref.year}`}
                                    </p>
                                    <div className="flex items-center gap-2 mb-2">
                                      <Badge variant="outline" className="text-xs">
                                        {ref.source}
                                      </Badge>
                                      {ref.document_type && (
                                        <Badge variant="outline" className="text-xs">
                                          {ref.document_type}
                                        </Badge>
                                      )}
                                      {ref.is_relevant !== null && (
                                        <Badge 
                                          variant="outline" 
                                          className={`text-xs ${
                                            ref.is_relevant 
                                              ? 'bg-green-100 text-green-700' 
                                              : 'bg-red-100 text-red-700'
                                          }`}
                                        >
                                          {ref.is_relevant ? 'Relevant' : 'Not Relevant'}
                                        </Badge>
                                      )}
                                    </div>
                                  </div>
                                  <div className="text-right">
                                    {ref.relevance_confidence !== null && (
                                      <div className="text-sm font-medium text-slate-900">
                                        {Math.round(ref.relevance_confidence * 100)}% Confidence
                                      </div>
                                    )}
                                    {ref.relevance_confidence !== null && (
                                      <Progress value={ref.relevance_confidence * 100} className="w-20 mt-1" />
                                    )}
                                  </div>
                                </div>
                                
                                {ref.top_line && (
                                  <div className="bg-slate-50 rounded-lg p-3 mb-3">
                                    <h5 className="font-medium text-slate-900 mb-1">Key Finding</h5>
                                    <p className="text-slate-700 text-sm">{ref.top_line}</p>
                                  </div>
                                )}

                                {ref.relevance_reason && (
                                  <div className="mb-3">
                                    <h5 className="font-medium text-slate-900 mb-1">Relevance</h5>
                                    <p className="text-slate-600 text-sm">{ref.relevance_reason}</p>
                                  </div>
                                )}

                                {ref.abstract_or_summary && (
                                  <div className="mb-3">
                                    <h5 className="font-medium text-slate-900 mb-1">Abstract</h5>
                                    <p className="text-slate-600 text-sm line-clamp-3">
                                      {ref.abstract_or_summary}
                                    </p>
                                  </div>
                                )}

                                <div className="flex items-center gap-2 pt-2 border-t border-slate-200">
                                  <span className="text-slate-500 text-xs">Status:</span>
                                  <Badge variant="outline" className="text-xs">
                                    {ref.acquisition_status || 'Unknown'}
                                  </Badge>
                                  <Badge variant="outline" className="text-xs">
                                    {ref.extraction_status || 'Unknown'}
                                  </Badge>
                                </div>
                              </CardContent>
                            </Card>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-8 text-gray-500">
                        No references available for this run
                      </div>
                    )}
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
} 
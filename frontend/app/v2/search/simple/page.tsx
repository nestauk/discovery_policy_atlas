'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import { Play, AlertCircle } from 'lucide-react'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import { useAPI } from '@/lib/api'

export default function SimpleSearchPage() {
  const [query, setQuery] = useState('')
  const [sources, setSources] = useState(['openalex', 'overton'])
  const [limit, setLimit] = useState(5)
  const [relevanceEnabled, setRelevanceEnabled] = useState(true)
  const [useAbstractsOnly, setUseAbstractsOnly] = useState(false)
  const [mode, setMode] = useState('semantic')
  const [booleanQuery, setBooleanQuery] = useState('')
  const [isCreatingProject, setIsCreatingProject] = useState(false)
  
  const router = useRouter()
  const { activeProject, setActiveProject } = useAnalysisProjectStore()
  const { createAnalysisProject, runAnalysisForProject } = useAPI()

  const handleSearch = async () => {
    if (!query.trim()) return
    
    let projectToUse = activeProject
    
    // If no active project, create one
    if (!activeProject) {
      try {
        setIsCreatingProject(true)
        const newProject = await createAnalysisProject({
          title: `Analysis: ${query.substring(0, 50)}${query.length > 50 ? '...' : ''}`,
          description: 'Auto-created project from search'
        })
        setActiveProject(newProject)
        projectToUse = newProject
      } catch (error) {
        console.error('Failed to create project:', error)
        alert('Failed to create project. Please try again.')
        return
      } finally {
        setIsCreatingProject(false)
      }
    }
    
    // Update project status to running
    setActiveProject({ ...projectToUse!, status: 'running' })
    
    // Prepare analysis configuration
    const analysisConfig = {
      query: query.trim(),
      sources,
      limit,
      relevance_enabled: relevanceEnabled,
      use_abstracts_only: useAbstractsOnly,
      mode,
      boolean_query: booleanQuery || undefined,
    }
    
    // Store search parameters and navigate to results page immediately
    const searchParams = new URLSearchParams()
    searchParams.set('query', query.trim())
    searchParams.set('project_id', projectToUse!.id)
    searchParams.set('sources', sources.join(','))
    searchParams.set('limit', limit.toString())
    searchParams.set('relevance_enabled', relevanceEnabled.toString())
    searchParams.set('use_abstracts_only', useAbstractsOnly.toString())
    searchParams.set('mode', mode)
    if (booleanQuery) {
      searchParams.set('boolean_query', booleanQuery)
    }
    
    // Start analysis asynchronously (don't wait for completion)
    runAnalysisForProject(projectToUse!.id, analysisConfig)
      .then((result) => {
        // Update project with results when complete
        setActiveProject({ 
          ...projectToUse!, 
          status: 'completed',
          run_id: result.run_id,
          total_references: result.total_references,
          relevant_references: result.relevant_references
        })
        console.log('Analysis completed:', result.run_id)
      })
      .catch((error) => {
        console.error('Analysis failed:', error)
        // Update project status to failed
        setActiveProject({ ...projectToUse!, status: 'failed' })
      })
    
    // Navigate to results page immediately (analysis will continue in background)
    router.push(`/v2/results?${searchParams.toString()}`)
  }

  return (
    <div className="flex-1 flex flex-col">
      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-4xl">
          {/* Header */}
          <div className="text-center mb-12">
            <div className="flex items-center justify-center gap-3 mb-4">
              <h1 className="text-4xl font-bold text-slate-900">
                Simple Search
              </h1>
              <Tooltip content={
                <p className="max-w-xs">
                  Alpha means this is an early prototype with limited functionality. 
                  Features may be incomplete, unstable, or subject to change. 
                  We&apos;re actively developing and improving the tool.
                </p>
              }>
                <Badge variant="default" className="text-xs bg-blue-600 hover:bg-blue-700 text-white font-semibold px-2 py-0.5 -mt-1">ALPHA</Badge>
              </Tooltip>
            </div>
            <p className="text-lg text-slate-600 max-w-2xl mx-auto">
              Direct search with advanced configuration options
            </p>
          </div>

          {/* Active Project Status */}
          {activeProject ? (
            <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
              <div className="flex items-center gap-2 text-blue-800">
                <AlertCircle className="h-4 w-4" />
                <span>
                  Running analysis for project: <strong>{activeProject.title}</strong>
                  {activeProject.status === 'running' && ' (Analysis in progress)'}
                </span>
              </div>
            </div>
          ) : (
            <div className="mb-6 bg-amber-50 border border-amber-200 rounded-lg p-4">
              <div className="flex items-center gap-2 text-amber-800">
                <AlertCircle className="h-4 w-4" />
                <span>
                  No project selected. A new project will be created automatically when you start the search.
                </span>
              </div>
            </div>
          )}

          {/* Search Configuration Card */}
          <Card className="border-0 shadow-lg">
            <CardContent className="p-8 space-y-6">
              {/* Research Question */}
              <div>
                <Label htmlFor="query" className="text-base font-medium text-slate-700">Research Question</Label>
                <textarea
                  id="query"
                  placeholder="e.g., What are the most effective parenting interventions?"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="w-full min-h-[120px] p-4 text-base border border-slate-200 rounded-md focus:border-blue-500 focus:ring-blue-500 resize-y mt-2"
                  style={{ resize: 'vertical' }}
                />
              </div>

              {/* Configuration Options */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <Label htmlFor="limit">Results Limit</Label>
                  <Input
                    id="limit"
                    type="number"
                    defaultValue={limit}
                    onChange={(e) => {
                      const value = parseInt(e.target.value)
                      if (!isNaN(value)) {
                        setLimit(value)
                      }
                    }}
                    min="1"
                    max="100"
                    className="mt-2"
                  />
                </div>

                <div>
                  <Label>Sources</Label>
                  <div className="flex gap-2 mt-2">
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
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <Label>Search Mode</Label>
                  <div className="flex gap-2 mt-2">
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

                <div className="space-y-3 mt-2">
                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="relevance"
                      checked={relevanceEnabled}
                      onChange={(e) => setRelevanceEnabled(e.target.checked)}
                    />
                    <Label htmlFor="relevance">Enable Relevance Filtering</Label>
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
              </div>

              {mode === 'boolean' && (
                <div>
                  <Label htmlFor="booleanQuery">Boolean Query</Label>
                  <Input
                    id="booleanQuery"
                    value={booleanQuery}
                    onChange={(e) => setBooleanQuery(e.target.value)}
                    placeholder="Enter boolean query (e.g., 'energy AND efficiency')"
                    className="mt-2"
                  />
                </div>
              )}

              {/* Search Button */}
              <div className="pt-4">
                <Button
                  onClick={handleSearch}
                  disabled={!query.trim() || sources.length === 0 || isCreatingProject}
                  className="w-full h-12 bg-blue-600 hover:bg-blue-700 text-base font-medium"
                >
                  {isCreatingProject ? (
                    <>
                      <Play className="mr-2 h-4 w-4 animate-spin" />
                      Creating Project...
                    </>
                  ) : (
                    <>
                      <Play className="mr-2 h-4 w-4" />
                      Start Analysis
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  )
}
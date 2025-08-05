'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ArrowLeft, MessageSquare, Edit3, Loader2 } from 'lucide-react'

export default function OptionsPage() {
  const [originalQuery, setOriginalQuery] = useState('')
  const [isEditing, setIsEditing] = useState(false)
  const [editingQuery, setEditingQuery] = useState('')
  const [suggestedRefinements, setSuggestedRefinements] = useState<Array<{
    category: string;
    title: string;
  }>>([])

  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const queryTextareaRef = useRef<HTMLTextAreaElement>(null)
  const router = useRouter()
  const urlSearchParams = useSearchParams()

  useEffect(() => {
    const query = urlSearchParams?.get('query') || ''
    console.log('Options page loaded with query:', query)
    setOriginalQuery(query)
    
    // Fetch AI suggestions when query is available
    if (query) {
      console.log('Fetching suggestions for query:', query)
      fetchSuggestions(query)
    } else {
      console.log('No query found in URL params')
    }
  }, [urlSearchParams])

  // Force re-fetch when component mounts or URL changes
  useEffect(() => {
    const query = urlSearchParams?.get('query') || ''
    if (query) {
      console.log('Component mounted/URL changed, query:', query)
      // Small delay to ensure component is fully mounted
      const timer = setTimeout(() => {
        if (query === urlSearchParams?.get('query')) {
          console.log('Fetching suggestions after delay for query:', query)
          fetchSuggestions(query)
        }
      }, 100)
      
      return () => clearTimeout(timer)
    }
  }, [urlSearchParams?.get('query')])

  const fetchSuggestions = async (query: string) => {
    console.log('Starting fetchSuggestions with query:', query)
    setIsLoading(true)
    setError(null)
    setSuggestedRefinements([]) // Clear previous suggestions
    
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      console.log('Making streaming API call to:', `${baseUrl}/api/agent/refine-query/stream`)
      
      const response = await fetch(`${baseUrl}/api/agent/refine-query/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: query,
          max_suggestions: 3
        })
      })
      
      console.log('Response status:', response.status)
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      
      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          
          if (done) break
          
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          
                    for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                if (data.suggestion) {
                  // Add the new suggestion to the list, avoiding duplicates
                  setSuggestedRefinements(prev => {
                    // Check if we already have this suggestion at this index
                    if (prev[data.index] && prev[data.index].title === data.suggestion.title) {
                      return prev
                    }
                    const newSuggestions = [...prev]
                    newSuggestions[data.index] = data.suggestion
                    return newSuggestions
                  })
                } else if (data.error) {
                  console.error('Stream error:', data.error)
                  setError(data.error)
                }
              } catch {
                console.log('Non-JSON line:', line)
              }
            }
          }
        }
      }
      
    } catch (err) {
      console.error('Failed to fetch suggestions:', err)
      setError('Failed to load AI suggestions. Using default suggestions.')
      // Fallback to default suggestions
      setSuggestedRefinements([
        {
          category: 'Public Health Policy',
          title: 'Comparative health impacts of vaping and smoking among youth'
        },
        {
          category: 'Regulation and Compliance',
          title: 'Regulatory frameworks for vaping and smoking: A global perspective'
        },
        {
          category: 'Evidence-Based Policy',
          title: 'Long-term effects of vaping versus traditional smoking on public health outcomes'
        }
      ])
    } finally {
      setIsLoading(false)
    }
  }



  const handleBack = () => {
    router.push('/agent')
  }

    const handleSelectOriginal = useCallback(async () => {
    console.log('handleSelectOriginal called')
    // Log the search
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      console.log('Logging original search to:', `${baseUrl}/api/agent/log-search`)
      console.log('Original search data:', {
        project_id: 'test-project',
        search_query: originalQuery
      })
      
      const response = await fetch(`${baseUrl}/api/agent/log-search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_id: 'test-project',
          search_query: originalQuery
        })
      })
      
      const result = await response.json()
      console.log('Log original search response:', result)
      
    } catch (err) {
      console.error('Failed to log search:', err)
      // Continue anyway - logging failure shouldn't block the user
    }

    const params = new URLSearchParams()
    params.set('query', originalQuery)
    params.set('finalQuery', originalQuery)
    router.push(`/agent/results?${params.toString()}`)
  }, [originalQuery, router])

  const handleEditQuery = (queryToEdit: string) => {
    setEditingQuery(queryToEdit)
    setIsEditing(true)
    // Scroll to top and focus the textarea
    setTimeout(() => {
      queryTextareaRef.current?.scrollIntoView({ behavior: 'smooth' })
      queryTextareaRef.current?.focus()
    }, 100)
  }

  const handleSaveEdit = () => {
    setOriginalQuery(editingQuery)
    setIsEditing(false)
  }

  const handleCancelEdit = () => {
    setEditingQuery(originalQuery)
    setIsEditing(false)
  }

  const handleSelectRefinement = useCallback(async (refinement: { title: string; category: string }) => {
    console.log('handleSelectRefinement called with:', refinement)
    // Log the search
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      console.log('Logging search to:', `${baseUrl}/api/agent/log-search`)
      console.log('Search data:', {
        project_id: 'test-project',
        search_query: refinement.title
      })
      
      const response = await fetch(`${baseUrl}/api/agent/log-search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_id: 'test-project',
          search_query: refinement.title
        })
      })
      
      const result = await response.json()
      console.log('Log search response:', result)
      
    } catch (err) {
      console.error('Failed to log search:', err)
      // Continue anyway - logging failure shouldn't block the user
    }

    const params = new URLSearchParams()
    params.set('query', originalQuery)
    params.set('finalQuery', refinement.title)
    params.set('category', refinement.category)
    router.push(`/agent/results?${params.toString()}`)
  }, [originalQuery, router])

  const handleSwitchToAI = () => {
    // For now just redirect to results with original query
    const params = new URLSearchParams()
    params.set('query', originalQuery)
    params.set('finalQuery', originalQuery)
    router.push(`/agent/results?${params.toString()}`)
  }

  return (
    <div className="flex-1 flex flex-col bg-slate-50 min-h-screen">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <div className="flex items-center gap-4">
          <Button 
            variant="ghost" 
            size="sm"
            onClick={handleBack}
            className="text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <div className="flex items-center gap-4 ml-auto">
            <Button 
              variant="outline"
              onClick={handleSwitchToAI}
              className="border-blue-200 text-blue-700 hover:bg-blue-50"
            >
              <MessageSquare className="h-4 w-4 mr-2" />
              Switch to AI Chat
            </Button>
            <Button 
              variant="outline"
              onClick={async () => {
                try {
                  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                  const response = await fetch(`${baseUrl}/api/agent/debug`);
                  const data = await response.json();
                  console.log('Debug response:', data);
                  alert('Check console for debug info');
                } catch (err) {
                  console.error('Debug error:', err);
                  alert('Debug failed - check console');
                }
              }}
              className="border-green-200 text-green-700 hover:bg-green-50"
            >
              Debug API
            </Button>
          </div>
        </div>
        <div className="mt-4">
          <h1 className="text-3xl font-bold text-slate-900">Refine your query</h1>
          {/* <p className="text-slate-600 mt-1">Choose a refined query for more targeted results</p> */}
        </div>
      </div>

      {/* Main Content */}
      <main className="flex-1 p-8 bg-slate-50">
        <div className="max-w-4xl mx-auto">
          {/* Editable Query Field */}
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              {/* <div className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center">
                <span className="text-blue-600 text-sm font-medium">🎯</span>
              </div> */}
              <h2 className="text-xl font-semibold text-slate-900">Your research question</h2>
            </div>
            
            {isEditing ? (
              <div className="space-y-4">
                <textarea
                  ref={queryTextareaRef}
                  value={editingQuery}
                  onChange={(e) => setEditingQuery(e.target.value)}
                  className="w-full min-h-[120px] p-4 text-base border border-slate-200 rounded-md focus:border-blue-500 focus:ring-blue-500 resize-y"
                  placeholder="Enter your research question..."
                />
                <div className="flex gap-3">
                  <Button onClick={handleSaveEdit} className="bg-blue-600 hover:bg-blue-700">
                    Save Changes
                  </Button>
                  <Button variant="outline" onClick={handleCancelEdit}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Card className="border-slate-200">
                <CardContent className="p-6">
                  <p className="text-lg text-slate-800 italic mb-4">&ldquo;{originalQuery}&rdquo;</p>
                  <div className="flex gap-3">
                    <Button onClick={() => {
                      console.log('Select original button clicked')
                      handleSelectOriginal()
                    }} className="bg-blue-600 hover:bg-blue-700">
                      Select Original Query
                    </Button>
                    <Button 
                      variant="outline" 
                      onClick={() => handleEditQuery(originalQuery)}
                      className="flex items-center gap-2"
                    >
                      <Edit3 className="h-4 w-4" />
                      Edit Query
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Suggested Refinements */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-6">
              {/* <Zap className="h-5 w-5 text-orange-500" /> */}
              <h2 className="text-xl font-semibold text-slate-900">Suggested refinements</h2>
              {isLoading && (
                <div className="flex items-center gap-2 text-slate-500">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="text-sm">Generating AI suggestions...</span>
                </div>
              )}
            </div>

            {error && (
              <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                <p className="text-sm text-yellow-800">{error}</p>
              </div>
            )}

            <div className="space-y-6">
              {suggestedRefinements.map((refinement, index) => (
                <Card key={index} className="border-slate-200 hover:border-slate-300 transition-all duration-200 cursor-pointer">
                  <CardContent className="p-6">
                    <div className="flex justify-between items-start">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-3">
                          <span className="text-sm font-medium text-blue-600 bg-blue-50 px-2 py-1 rounded">
                            {refinement.category}
                          </span>
                          <span className="text-xs text-slate-500">→</span>
                        </div>
                        
                        <h3 className="text-lg font-semibold text-slate-900 mb-3">
                          &ldquo;{refinement.title}&rdquo;
                        </h3>
                        

                      </div>
                      
                      <div className="flex flex-col gap-2">
                        <Button
                          onClick={() => {
                            console.log('Select button clicked for refinement:', refinement)
                            handleSelectRefinement(refinement)
                          }}
                          className="bg-blue-600 hover:bg-blue-700"
                        >
                          Select
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleEditQuery(refinement.title)}
                          className="flex items-center gap-2 text-xs"
                        >
                          <Edit3 className="h-3 w-3" />
                          Edit
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>

          {/* Bottom Actions */}
          <div className="text-center">
            <div className="bg-slate-50 rounded-lg p-6">
              <h3 className="font-semibold text-slate-900 mb-2">
                Want something different?
              </h3>
              <p className="text-slate-600 text-sm mb-4">
                Switch to our AI chat assistant for more personalized refinements
              </p>
              <Button 
                variant="outline"
                onClick={handleSwitchToAI}
                className="border-blue-200 text-blue-700 hover:bg-blue-50"
              >
                <MessageSquare className="h-4 w-4 mr-2" />
                Try AI Chat Instead
              </Button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ArrowLeft, MessageSquare, Zap, FileText } from 'lucide-react'

const quickSuggestions = [
  {
    category: 'Public Health Policy',
    title: 'Comparative health impacts of vaping and smoking among youth',
    description: 'Focusing on youth allows for insight into preventative policies and the implications of nicotine exposure during adolescence.'
  },
  {
    category: 'Regulation and Compliance', 
    title: 'Regulatory frameworks for vaping and smoking: A global perspective',
    description: 'Understanding different regulatory responses globally can inform policy recommendations for effective tobacco control.'
  }
]

export default function RefineSearchPage() {
  const [originalQuery, setOriginalQuery] = useState('')
  const [searchParams, setSearchParams] = useState<{
    query: string;
    role: string;
    geographic: string;
    urgency: string;
    policyAreas: string[];
  }>({
    query: '',
    role: '',
    geographic: '',
    urgency: '',
    policyAreas: []
  })
  const router = useRouter()
  const urlSearchParams = useSearchParams()

  useEffect(() => {
    const query = urlSearchParams?.get('query') || ''
    const role = urlSearchParams?.get('role') || ''
    const geographic = urlSearchParams?.get('geographic') || ''
    const urgency = urlSearchParams?.get('urgency') || ''
    const policyAreas = urlSearchParams?.get('policyAreas')?.split(',') || []

    setOriginalQuery(query)
    setSearchParams({
      query,
      role,
      geographic,
      urgency,
      policyAreas
    })
  }, [urlSearchParams])

  const handleBackToSearch = () => {
    router.push('/agent')
  }

  const handleQuickSuggestion = (suggestion: { title: string }) => {
    const params = new URLSearchParams()
    params.set('query', searchParams.query || '')
    params.set('role', searchParams.role || '')
    params.set('geographic', searchParams.geographic || '')
    params.set('urgency', searchParams.urgency || '')
    params.set('policyAreas', Array.isArray(searchParams.policyAreas) ? searchParams.policyAreas.join(',') : '')
    params.set('refinedQuery', suggestion.title)
    router.push(`/agent/options?${params.toString()}`)
  }

  const handleStartAIChat = () => {
    const params = new URLSearchParams()
    params.set('query', searchParams.query || '')
    params.set('role', searchParams.role || '')
    params.set('geographic', searchParams.geographic || '')
    params.set('urgency', searchParams.urgency || '')
    params.set('policyAreas', Array.isArray(searchParams.policyAreas) ? searchParams.policyAreas.join(',') : '')
    router.push(`/agent/options?${params.toString()}`)
  }

  return (
    <div className="flex-1 flex flex-col">
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <div className="flex items-center gap-4">
          <Button 
            variant="ghost" 
            size="sm"
            onClick={handleBackToSearch}
            className="text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Search
          </Button>
        </div>
        <div className="mt-4">
          <h1 className="text-2xl font-bold text-slate-900">Refine Your Search</h1>
          <p className="text-slate-600 mt-1">Choose how you&apos;d like to improve your research question</p>
        </div>
      </div>

      <main className="flex-1 p-8">
        <div className="max-w-6xl mx-auto">
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center">
                <span className="text-blue-600 text-sm font-medium">🎯</span>
              </div>
              <h2 className="text-lg font-semibold text-slate-900">Original Query</h2>
            </div>
            <Card className="border-slate-200">
              <CardContent className="p-6">
                <p className="text-lg text-slate-800 italic">&ldquo;{originalQuery}&rdquo;</p>
                <p className="text-sm text-slate-600 mt-4">
                  For quick results, try the suggested refinements. For more tailored questions, use the AI chat.
                </p>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div>
              <div className="flex items-center gap-3 mb-6">
                <div className="flex items-center gap-2">
                  <Zap className="h-5 w-5 text-orange-500" />
                  <h2 className="text-xl font-semibold text-slate-900">Quick Suggestions</h2>
                </div>
                <span className="px-2 py-1 bg-orange-100 text-orange-700 text-xs font-medium rounded">
                  Fast
                </span>
              </div>
              <p className="text-slate-600 mb-6">
                Choose from AI-generated refinements based on your question
              </p>
              
              <div className="space-y-4">
                {quickSuggestions.map((suggestion, index) => (
                  <Card key={index} className="border-slate-200 hover:border-orange-300 transition-colors cursor-pointer">
                    <CardContent className="p-6">
                      <div className="flex justify-between items-start mb-3">
                        <span className="text-sm font-medium text-blue-600">
                          {suggestion.category}
                        </span>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleQuickSuggestion(suggestion)}
                          className="ml-4"
                        >
                          Select
                        </Button>
                      </div>
                      <h3 className="font-semibold text-slate-900 mb-2">
                        &ldquo;{suggestion.title}&rdquo;
                      </h3>
                      <p className="text-sm text-slate-600">
                        {suggestion.description}
                      </p>
                    </CardContent>
                  </Card>
                ))}
              </div>

              <div className="mt-6 text-center">
                <Button 
                  variant="outline" 
                  className="w-full"
                  onClick={() => {
                    const params = new URLSearchParams()
                    params.set('query', searchParams.query || '')
                    params.set('role', searchParams.role || '')
                    params.set('geographic', searchParams.geographic || '')
                    params.set('urgency', searchParams.urgency || '')
                    params.set('policyAreas', Array.isArray(searchParams.policyAreas) ? searchParams.policyAreas.join(',') : '')
                    router.push(`/agent/options?${params.toString()}`)
                  }}
                >
                  <FileText className="h-4 w-4 mr-2" />
                  View All Suggestions
                </Button>
              </div>

              <div className="mt-4 flex items-center justify-center text-sm text-slate-500">
                <span>💡 Perfect when you need results quickly</span>
              </div>
            </div>

            <div>
              <div className="flex items-center gap-3 mb-6">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-5 w-5 text-blue-500" />
                  <h2 className="text-xl font-semibold text-slate-900">AI Chat Assistant</h2>
                </div>
                <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded">
                  Interactive
                </span>
              </div>
              <p className="text-slate-600 mb-6">
                Have a conversation with AI to perfectly tailor your question
              </p>

              <Card className="border-slate-200">
                <CardContent className="p-6">
                  <div className="bg-slate-50 rounded-lg p-4 mb-6">
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center">
                        <MessageSquare className="h-4 w-4 text-white" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-900 mb-2">
                          &ldquo;What specific outcomes are you most interested in regarding this topic?&rdquo;
                        </p>
                        <p className="text-xs text-slate-500">Example AI question</p>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-sm text-slate-600">
                      <span>💬</span>
                      <span>Personalized questions based on your responses</span>
                    </div>
                    <div className="flex items-center gap-2 text-sm text-slate-600">
                      <span>🤖</span>
                      <span>Best for complex or nuanced research questions</span>
                    </div>
                  </div>

                  <Button
                    onClick={handleStartAIChat}
                    className="w-full mt-6 bg-blue-600 hover:bg-blue-700"
                  >
                    <MessageSquare className="h-4 w-4 mr-2" />
                    Start AI Conversation
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>

          <div className="mt-12 text-center">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-6">
              <h3 className="font-semibold text-amber-900 mb-2">
                💡 Not sure which to choose?
              </h3>
              <p className="text-amber-800 text-sm">
                Quick Suggestions work great for straightforward topics where you want immediate refinements. AI Chat is better when you need to explore different angles or have a complex, multi-faceted research question.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
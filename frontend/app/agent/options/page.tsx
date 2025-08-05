'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ArrowLeft, MessageSquare, Edit3 } from 'lucide-react'

const suggestedRefinements = [
  {
    category: 'Public Health Policy',
    title: 'Comparative health impacts of vaping and smoking among youth',
    description: 'Focusing on youth allows for insight into preventative policies and the implications of nicotine exposure during adolescence.'
  },
  {
    category: 'Regulation and Compliance',
    title: 'Regulatory frameworks for vaping and smoking: A global perspective', 
    description: 'Understanding different regulatory responses globally can inform policy recommendations for effective tobacco control.'
  },
  {
    category: 'Evidence-Based Policy',
    title: 'Long-term effects of vaping versus traditional smoking on public health outcomes',
    description: 'This query aims to uncover longitudinal studies that can provide data relevant for policy decision-making regarding public health strategies.'
  }
]

export default function OptionsPage() {
  const [originalQuery, setOriginalQuery] = useState('')
  const [isEditing, setIsEditing] = useState(false)
  const [editingQuery, setEditingQuery] = useState('')
  const queryTextareaRef = useRef<HTMLTextAreaElement>(null)
  const router = useRouter()
  const urlSearchParams = useSearchParams()

  useEffect(() => {
    const query = urlSearchParams?.get('query') || ''
    setOriginalQuery(query)
  }, [urlSearchParams])

  const handleBack = () => {
    router.push('/agent')
  }

  const handleSelectOriginal = () => {
    const params = new URLSearchParams()
    params.set('query', originalQuery)
    params.set('finalQuery', originalQuery)
    router.push(`/agent/results?${params.toString()}`)
  }

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

  const handleSelectRefinement = (refinement: { title: string; category: string }) => {
    const params = new URLSearchParams()
    params.set('query', originalQuery)
    params.set('finalQuery', refinement.title)
    params.set('category', refinement.category)
    router.push(`/agent/results?${params.toString()}`)
  }

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
                    <Button onClick={handleSelectOriginal} className="bg-blue-600 hover:bg-blue-700">
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
            </div>

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
                        
                        <p className="text-slate-600 text-sm leading-relaxed">
                          {refinement.description}
                        </p>
                      </div>
                      
                      <div className="flex flex-col gap-2">
                        <Button
                          onClick={() => handleSelectRefinement(refinement)}
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
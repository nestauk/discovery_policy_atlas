'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { DocumentDetailView } from '@/components/search/document-detail-view'
import { 
  Upload,
  FileText,
  Loader2,
  AlertCircle,
  Settings,
  ChevronRight,
  ChevronDown,
  Zap,
  RotateCcw
} from 'lucide-react'
import { useAPI } from '@/lib/api'

// Types for test extraction results
interface ExtractionResult {
  document: {
    id: string
    doc_id: string
    title: string
    source: string
    year?: number
    abstract_or_summary?: string
    is_relevant?: boolean
    extraction_status?: string
  }
  extraction: {
    issues: Array<{
      idx?: number
      label?: string
      explanation?: string
      supporting_quote?: string
    }>
    interventions: Array<{
      idx?: number
      name?: string
      description?: string
      type?: string
      country?: string
      study_type?: string
      supporting_quote?: string
      addresses_issues?: number[]
      results?: Array<{
        outcome_variable?: string
        effect_direction?: string
        effect_size_type?: string
        effect_size?: string
        uncertainty?: string
        p_value?: string
        population_measured?: string
        subgroup_or_dose?: string
        result_text?: string
        supporting_quote?: string
      }>
    }>
    mappings?: unknown[]
    conclusion?: {
      top_line_summary?: string
      detailed_explanation?: string
      supporting_quote?: string
    }
    metadata?: {
      text_length?: number
      extraction_time?: string
      custom_prompts_used?: boolean
      [key: string]: unknown
    }
  }
}
type DefaultPrompts = Record<string, string>

export default function TestExtractionPage() {
  const { fetchWithAuth } = useAPI()
  
  // Input state
  const [inputType, setInputType] = useState<'text' | 'file'>('text')
  const [textInput, setTextInput] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  
  // Simplified state
  const [showPrompts, setShowPrompts] = useState(false)
  const [defaultPrompts, setDefaultPrompts] = useState<DefaultPrompts>({})
  const [customPrompts, setCustomPrompts] = useState<DefaultPrompts>({})
  const [promptsLoaded, setPromptsLoaded] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<ExtractionResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      if (file.type !== 'application/pdf') {
        setError('Please select a PDF file')
        return
      }
      setSelectedFile(file)
      setError(null)
    }
  }

  // Load default prompts when expanding prompts section
  const loadDefaultPrompts = async () => {
    if (promptsLoaded) return
    
    try {
      const response = await fetchWithAuth('/api/test-extraction/prompts', { method: 'GET' })
      setDefaultPrompts(response)
      setCustomPrompts(response) // Initialize custom prompts with defaults
      setPromptsLoaded(true)
    } catch (err) {
      console.error('Failed to load default prompts:', err)
    }
  }

  const resetCustomPrompts = () => setCustomPrompts(defaultPrompts)

  const runExtraction = async () => {
    if (!textInput.trim() && !selectedFile) {
      setError('Please provide either text or upload a PDF file')
      return
    }

    setIsLoading(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()
      
      if (selectedFile) {
        formData.append('file', selectedFile)
      } else {
        formData.append('text', textInput)
      }

      // Add custom prompts if any are set
      const filteredPrompts = Object.fromEntries(
        Object.entries(customPrompts).filter(([, value]) => value?.trim())
      )
      
      if (Object.keys(filteredPrompts).length > 0) {
        formData.append('custom_prompts', JSON.stringify(filteredPrompts))
      }

      const response = await fetchWithAuth('/api/test-extraction', {
        method: 'POST',
        body: formData,
      })

      setResult(response)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Extraction failed')
    } finally {
      setIsLoading(false)
    }
  }

  const clearAll = () => {
    setTextInput('')
    setSelectedFile(null)
    setResult(null)
    setError(null)
    setCustomPrompts(defaultPrompts) // Reset to defaults instead of empty
    // Reset file input
    const fileInput = document.getElementById('file-input') as HTMLInputElement
    if (fileInput) fileInput.value = ''
  }

  return (
    <div className="flex-1 bg-slate-50 p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">Test Extraction</h1>
        </div>

        {/* Input Section */}
        <Card>
          <CardContent className="space-y-4">
            {/* Input Type Selection */}
            <div className="flex gap-4">
              <Button
                variant={inputType === 'text' ? 'default' : 'outline'}
                onClick={() => setInputType('text')}
                className="flex items-center gap-2"
              >
                <FileText className="h-4 w-4" />
                Paste Text
              </Button>
              <Button
                variant={inputType === 'file' ? 'default' : 'outline'}
                onClick={() => setInputType('file')}
                className="flex items-center gap-2"
              >
                <Upload className="h-4 w-4" />
                Upload PDF
              </Button>
            </div>

            {/* Text Input */}
            {inputType === 'text' && (
              <div className="space-y-2">
                <Textarea
                  id="text-input"
                  placeholder="Paste the document text you want to extract issues, interventions and results from..."
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  className="min-h-[200px]"
                />
                <p className="text-sm text-slate-500 pt-2">
                  {textInput.length} characters
                </p>
              </div>
            )}

            {/* File Input */}
            {inputType === 'file' && (
              <div className="space-y-2">
                <Label htmlFor="file-input">Select PDF file</Label>
                <Input
                  id="file-input"
                  type="file"
                  accept=".pdf"
                  onChange={handleFileSelect}
                  className="cursor-pointer"
                />
                {selectedFile && (
                  <div className="flex items-center gap-2 text-sm text-slate-600">
                    <FileText className="h-4 w-4" />
                    {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Advanced Settings - Custom Prompts */}
        <Card>
          <Collapsible open={showPrompts} onOpenChange={(open) => {
            setShowPrompts(open)
            if (open) loadDefaultPrompts()
          }}>
            <CollapsibleTrigger asChild>
              <CardHeader className="cursor-pointer hover:bg-slate-50">
                <CardTitle className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Settings className="h-5 w-5" />
                    Advanced - Customise prompts
                    <Badge variant="outline" className="ml-2">Optional</Badge>
                  </div>
                  {showPrompts ? 
                    <ChevronDown className="h-4 w-4" /> : 
                    <ChevronRight className="h-4 w-4" />
                  }
                </CardTitle>
              </CardHeader>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <CardContent className="pt-0 space-y-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm text-slate-600">
                    
                  </p>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={resetCustomPrompts}
                    className="flex items-center gap-1"
                  >
                    <RotateCcw className="h-3 w-3" />
                    Reset
                  </Button>
                </div>

                <div className="space-y-4">
                  {/* Show loading state or actual prompts */}
                  {!promptsLoaded ? (
                    <div className="text-center py-4">
                      <p className="text-sm text-slate-500">Loading default prompts...</p>
                    </div>
                  ) : (
                    <>
                      {[
                        { key: 'issues', label: 'Issues' },
                        { key: 'interventions', label: 'Interventions' },
                        { key: 'mappings', label: 'Mappings (Issues - Interventions)' },
                        { key: 'results', label: 'Results' },
                        { key: 'conclusions', label: 'Conclusions' }
                      ].map(({ key, label }) => (
                        <div key={key} className="space-y-2">
                          <Label htmlFor={`${key}-prompt`} className="font-bold">{label} Prompt</Label>
                          <Textarea
                            id={`${key}-prompt`}
                            placeholder={`Loading ${label.toLowerCase()} prompt...`}
                            value={customPrompts[key] || ''}
                            onChange={(e) => setCustomPrompts(prev => ({ ...prev, [key]: e.target.value }))}
                            className="min-h-[120px] text-xs font-mono"
                          />
                        </div>
                      ))}
                    </>
                  )}
                </div>
              </CardContent>
            </CollapsibleContent>
          </Collapsible>
        </Card>

        {/* Action Buttons */}
        <div className="flex gap-4">
          <Button 
            onClick={runExtraction}
            disabled={isLoading || (!textInput.trim() && !selectedFile)}
            className="flex items-center gap-2"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Zap className="h-4 w-4" />
            )}
            {isLoading ? 'Extracting...' : 'Run Extraction'}
          </Button>
          
          <Button variant="outline" onClick={clearAll}>
            Clear All
          </Button>
        </div>

        {/* Error Message */}
        {error && (
          <Card className="border-red-200">
            <CardContent className="p-4">
              <div className="flex items-center gap-2 text-red-600">
                <AlertCircle className="h-4 w-4" />
                <span className="text-sm font-medium">{error}</span>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Results */}
        {result && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5" />
                Extraction Results
              </CardTitle>
              {result.extraction.metadata && (
                <div className="flex gap-2 flex-wrap">
                  <Badge variant="outline">
                    {result.extraction.metadata.text_length} chars
                  </Badge>
                  {result.extraction.metadata.custom_prompts_used && (
                    <Badge variant="outline" className="bg-blue-50 text-blue-700">
                      Custom prompts used
                    </Badge>
                  )}
                </div>
              )}
            </CardHeader>
            <CardContent>
              <DocumentDetailView 
                extraction={result.extraction}
              />
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
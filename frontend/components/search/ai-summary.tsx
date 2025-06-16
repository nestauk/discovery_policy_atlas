import { useState } from 'react'
import { useAPI } from '@/lib/api'
import { Paper } from '@/types/search'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'

interface AiSummaryProps {
  papers: Paper[]
  extractionFields: string[]
}

const TEMPLATES = {
  short: 'Write a short, high-level summary of the main findings and themes.',
  detailed: 'Write a detailed, in-depth summary covering all key findings, themes, and nuances from the papers.'
}

export function AiSummary({ papers, extractionFields }: AiSummaryProps) {
  const [summary, setSummary] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [prompt, setPrompt] = useState('')
  const { fetchWithAuth } = useAPI()

  const handleGenerate = async () => {
    setLoading(true)
    setSummary('')
    setError('')
    try {
      const data = await fetchWithAuth('/api/summary', {
        method: 'POST',
        body: JSON.stringify({ papers, extraction_fields: extractionFields, prompt }),
      })
      setSummary(data.summary)
    } catch (err) {
      console.error('Summary generation error:', err)
      setError('Failed to generate summary. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleTemplate = (template: keyof typeof TEMPLATES) => {
    setPrompt(TEMPLATES[template])
  }

  return (
    <Card className="mt-8 max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle>AI Summary</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="flex flex-col md:flex-row md:items-end gap-4">
            <div className="flex-1 space-y-2">
              <Label htmlFor="ai-summary-prompt">Instructions (optional)</Label>
              <textarea
                id="ai-summary-prompt"
                className="border-input focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] rounded-md border bg-transparent px-3 py-2 text-base shadow-xs w-full min-h-[60px] placeholder:text-muted-foreground"
                placeholder="Add custom instructions for the summary (optional)"
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                rows={3}
              />
            </div>
            <div className="flex flex-col gap-2 min-w-[160px]">
              <Button type="button" variant="outline" onClick={() => handleTemplate('short')}>
                Short summary
              </Button>
              <Button type="button" variant="outline" onClick={() => handleTemplate('detailed')}>
                Detailed summary
              </Button>
            </div>
          </div>
          <Button
            className="w-full"
            onClick={handleGenerate}
            disabled={loading || !papers.length}
          >
            {loading ? 'Generating summary...' : 'Generate AI Summary'}
          </Button>
          {error && <div className="text-destructive mt-2">{error}</div>}
          {summary && (
            <>
              <style>{`
                .ai-summary-link { color: #2563eb; text-decoration: underline; transition: color 0.2s;}
                .ai-summary-link:hover { color: #1e40af; }
              `}</style>
              <div className="summary-content mt-6 bg-gray-50 rounded p-4 border border-gray-200">
                <h3 className="text-lg font-semibold mb-2">AI Summary</h3>
                {/* LLM output is treated as trusted HTML (not user input) */}
                <div dangerouslySetInnerHTML={{ __html: summary }} />
              </div>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

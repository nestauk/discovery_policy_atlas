import { useState } from 'react'
import { useAPI } from '@/lib/api'
import { Paper } from '@/types/search'

interface AiSummaryProps {
  papers: Paper[]
  extractionFields: string[]
}

export function AiSummary({ papers, extractionFields }: AiSummaryProps) {
  const [summary, setSummary] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { fetchWithAuth } = useAPI()

  const handleGenerate = async () => {
    setLoading(true)
    setSummary('')
    setError('')
    try {
      const data = await fetchWithAuth('/api/summary', {
        method: 'POST',
        body: JSON.stringify({ papers, extraction_fields: extractionFields }),
      })
      setSummary(data.summary)
    } catch (err) {
      console.error('Summary generation error:', err)
      setError('Failed to generate summary. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="ai-summary-box mt-6">
      <button className="btn" onClick={handleGenerate} disabled={loading || !papers.length}>
        {loading ? 'Generating summary...' : 'Generate AI Summary'}
      </button>
      {error && <div className="text-destructive mt-2">{error}</div>}
      {summary && (
        <div className="summary-content mt-4">
          <h3 className="text-lg font-semibold mb-2">AI Summary</h3>
          <p>{summary}</p>
        </div>
      )}
    </div>
  )
}

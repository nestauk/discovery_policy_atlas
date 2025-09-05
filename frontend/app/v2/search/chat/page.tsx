'use client'

import { useRouter } from 'next/navigation'
import { useAPI } from '@/lib/api'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import ChatInterface from './ChatInterface'

export default function ChatSearchPage() {
  const router = useRouter()
  const { createAnalysisProject, runAnalysisForProject } = useAPI()
  const { setActiveProject } = useAnalysisProjectStore()

  const handleRunAnalysis = async (brief: {
    researchQuestion: string;
    subQuestions: string[];
    direct: {
      query: string;
      sources: string[];
      limit: number;
      relevanceFiltering: boolean;
      abstractsOnly: boolean;
      mode: string;
      geography?: string[];
      access: { academic: boolean; policy: boolean };
      timeFrom?: string;
      timeTo?: string;
    };
  }) => {
    try {
      // Create analysis project from chat brief
      const project = await createAnalysisProject({
        title: `Chat Search: ${brief.researchQuestion}`,
        description: brief.subQuestions.length > 0 
          ? `Sub-questions: ${brief.subQuestions.join('; ')}` 
          : undefined
      })

      // Set as active project
      setActiveProject(project)

      // Prepare analysis configuration from chat brief
      const analysisConfig = {
        query: brief.direct.query,
        sources: brief.direct.sources,
        limit: brief.direct.limit,
        relevance_enabled: brief.direct.relevanceFiltering,
        use_abstracts_only: brief.direct.abstractsOnly,
        mode: brief.direct.mode,
        // New chat-specific parameters
        geography_filter: brief.direct.geography,
        access_types: Object.entries(brief.direct.access)
          .filter(([, enabled]) => enabled)
          .map(([key]) => key),
        sub_questions: brief.subQuestions,
        // Time parameters
        date_from: brief.direct.timeFrom,
        date_to: brief.direct.timeTo,
      }

      // Start analysis (don't wait for completion)
      runAnalysisForProject(project.id, analysisConfig)
        .then((result) => {
          console.log('Chat analysis completed:', result.run_id)
          setActiveProject({ 
            ...project, 
            status: 'completed',
            run_id: result.run_id,
            total_references: result.total_references,
            relevant_references: result.relevant_references
          })
        })
        .catch((error) => {
          console.error('Chat analysis failed:', error)
          setActiveProject({ ...project, status: 'failed' })
        })

      // Navigate to results immediately
      router.push(`/v2/results?project_id=${project.id}`)
      
    } catch (error) {
      console.error('Failed to start chat analysis:', error)
      alert('Failed to start analysis. Please try again.')
    }
  }

  return <ChatInterface onRunAnalysis={handleRunAnalysis} />
}
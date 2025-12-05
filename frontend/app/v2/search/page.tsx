'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAPI } from '@/lib/api'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import SearchWizard, { SearchContext } from './chat/SearchWizard'

export default function SearchPage() {
  const router = useRouter()
  const { createAnalysisProject, runAnalysisForProject } = useAPI()
  const { setActiveProject } = useAnalysisProjectStore()
  const [isRunning, setIsRunning] = useState(false)

  const handleRunAnalysis = async (context: SearchContext) => {
    // Prevent user initiating multiple analysis runs with the same search parameters
    if (isRunning) return;
    
    setIsRunning(true);
    try {
      // Create analysis project from search context
      const project = await createAnalysisProject({
        title: context.researchQuestion || 'New Analysis Project',
        // Additional questions step is currently skipped
        // description: context.additionalQuestions.length > 0 
        //   ? `Additional questions: ${context.additionalQuestions.join('; ')}` 
        //   : undefined
      })

      // Set as active project
      setActiveProject(project)

      // Convert time preset to actual dates
      let dateFrom: string | undefined;
      let dateTo: string | undefined;
      
      if (context.parameters.timePreset === "CUSTOM") {
        dateFrom = context.parameters.customFrom;
        dateTo = context.parameters.customTo;
      } else if (context.parameters.timePreset !== "ANY") {
        const now = new Date();
        dateTo = now.toISOString().split('T')[0]; // today
        
        switch (context.parameters.timePreset) {
          case "LAST_YEAR":
            dateFrom = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate()).toISOString().split('T')[0];
            break;
          case "LAST_5_YEARS":
            dateFrom = new Date(now.getFullYear() - 5, now.getMonth(), now.getDate()).toISOString().split('T')[0];
            break;
          case "LAST_10_YEARS":
            dateFrom = new Date(now.getFullYear() - 10, now.getMonth(), now.getDate()).toISOString().split('T')[0];
            break;
          case "SINCE_2000":
            dateFrom = "2000-01-01";
            break;
        }
      }

      // TODO: Backend needs to be updated to handle SearchContext directly
      // For now, convert to old format - backend will generate query from context
      // The query here is just a placeholder - backend should use the full context
      const analysisConfig = {
        query: context.researchQuestion, // Backend will use this + context to generate proper query
        sources: context.parameters.sources,
        limit: context.maxResults,
        relevance_enabled: true,
        use_abstracts_only: false,
        mode: "semantic", // Always semantic for now
        // Pass the full context as metadata
        geography_filter: context.parameters.geography,
        access_types: Object.entries(context.parameters.access)
          .filter(([, enabled]) => enabled)
          .map(([key]) => key),
        sub_questions: [], // Additional questions step is currently skipped
        // Time parameters
        date_from: dateFrom,
        date_to: dateTo,
        // New SearchContext fields - pass as metadata
        search_context: {
          research_question: context.researchQuestion,
          population: context.population,
          outcome: context.outcome,
          parameters: context.parameters,
          screening_factors: context.screeningFactors,
          additional_questions: [], // Additional questions step is currently skipped
          max_results: context.maxResults,
        },
      }

      // Start analysis (don't wait for completion)
      runAnalysisForProject(project.id, analysisConfig)
        .then((result) => {
          console.log('Search analysis completed:', result.run_id)
          setActiveProject({ 
            ...project, 
            status: 'completed',
            run_id: result.run_id,
            total_references: result.total_references,
            relevant_references: result.relevant_references
          })
        })
        .catch((error) => {
          console.error('Search analysis failed:', error)
          setActiveProject({ ...project, status: 'failed' })
        })

      // Navigate to results immediately
      router.push(`/v2/results?project_id=${project.id}`)
      
    } catch (error) {
      console.error('Failed to start search analysis:', error)
      alert('Failed to start analysis. Please try again.')
    } finally {
      setIsRunning(false);
    }
  }

  return <SearchWizard onRunAnalysis={handleRunAnalysis} isRunning={isRunning} />
}
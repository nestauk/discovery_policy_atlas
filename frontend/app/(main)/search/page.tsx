'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAPI } from '@/lib/api'
import { useAnalysisProjectStore } from '@/lib/analysisProjectStore'
import SearchWizard, { SearchContext, useWizard } from '@/components/search/SearchWizard'

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
      // Read refine state from wizard store
      const { parentProjectId } = useWizard.getState()
      const baseTitle = (context.researchQuestion || 'New Analysis Project').replace(/ \(refined\)$/, '')

      // Create analysis project from search context
      const project = await createAnalysisProject({
        title: parentProjectId ? `${baseTitle} (refined)` : baseTitle,
        parent_project_id: parentProjectId ?? undefined,
      })

      // Reset wizard state so a fresh visit to /search starts clean
      useWizard.getState().reset()

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
          case "LAST_2_YEARS":
            dateFrom = new Date(now.getFullYear() - 2, now.getMonth(), now.getDate()).toISOString().split('T')[0];
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

      const normaliseConstraint = (value: string | undefined) => {
        if (!value || value === 'Any') {
          return undefined
        }
        return value.toLowerCase()
      }
      const implementationConstraints = {
        cost: normaliseConstraint(context.implementationConstraints.cost),
        staffing: normaliseConstraint(context.implementationConstraints.staffing),
        implementation_complexity: normaliseConstraint(
          context.implementationConstraints.implementationComplexity,
        ),
      }
      const hasImplementationConstraints = Object.values(
        implementationConstraints,
      ).some(Boolean)

      const searchContext = {
        research_question: context.researchQuestion,
        population: context.population,
        inner_setting: context.innerSetting,
        outcome: context.outcome,
        screening_factors: context.screeningFactors,
        sources: context.parameters.sources,
        geography: context.parameters.geography,
        time_preset: context.parameters.timePreset,
        time_from: dateFrom,
        time_to: dateTo,
        max_results: context.maxResults,
        additional_questions: context.additionalQuestions,
        ...(hasImplementationConstraints
          ? { implementation_constraints: implementationConstraints }
          : {}),
      }

      const analysisConfig = {
        query: context.researchQuestion,
        sources: context.parameters.sources,
        limit: context.maxResults,
        relevance_enabled: true,
        use_abstracts_only: false,
        mode: "semantic", // Always semantic for now
        geography_filter: context.parameters.geography,
        access_types: Object.entries(context.parameters.access)
          .filter(([, enabled]) => enabled)
          .map(([key]) => key),
        sub_questions: [], // Additional questions step is currently skipped
        date_from: dateFrom,
        date_to: dateTo,
        search_context: searchContext,
      }

      // Fire-and-forget — the project page handles status via polling
      runAnalysisForProject(project.id, analysisConfig)
        .then((result) => {
          console.log('Search analysis completed:', result.run_id)
        })
        .catch((error) => {
          console.error('Search analysis HTTP connection lost (backend may still be running):', error)
        })

      // Navigate to results immediately
      router.push(`/projects/${project.id}`)
      
    } catch (error) {
      console.error('Failed to start search analysis:', error)
      alert('Failed to start analysis. Please try again.')
    } finally {
      setIsRunning(false);
    }
  }

  return <SearchWizard onRunAnalysis={handleRunAnalysis} isRunning={isRunning} />
}
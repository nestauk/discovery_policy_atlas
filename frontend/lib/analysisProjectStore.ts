import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface AnalysisProject {
  id: string
  run_id?: string
  title: string
  description?: string
  query?: string
  total_references: number
  relevant_references: number
  status: 'created' | 'running' | 'synthesising' | 'completed' | 'failed' | 'uploading'
  created_at: string
  created_by_user_id?: string
  created_by_name?: string
  search_query?: {
    original_query?: string
    boolean_query?: string
    sub_questions?: string[]
    sources?: string[]
    access_types?: string[]
    geography_filter?: string[]
    time_preset?: string
    time_from?: string
    time_to?: string
    limit?: number
    mode?: string
    scope?: string[]
    custom_focus?: string[]
    excludes?: string[]
    custom_excludes?: string[]
    relevance_enabled?: boolean
    use_abstracts_only?: boolean
  }
}

export interface AnalysisDocument {
  id: string
  analysis_project_id: string
  doc_id: string
  source: string
  source_id?: string
  title?: string
  abstract_or_summary?: string
  year?: number
  doi?: string
  authors?: string[]
  landing_page_url?: string
  pdf_url?: string
  is_oa?: boolean
  document_type?: string
  author_institution_countries?: string[]
  // Relevance fields
  is_relevant?: boolean
  relevance_confidence?: number
  relevance_reason?: string
  top_line?: string
  document_type_reason?: string
  // Acquisition fields
  acquisition_status?: string
  acquisition_error?: string
  full_text_available?: boolean
  file_path?: string
  // Extraction fields
  extraction_status?: string
  extraction_error?: string
  text_source?: string
  extraction_results?: Record<string, unknown>
  // Additional fields
  citation_count?: number
  venue?: string
  topics?: string[]
  source_country?: string
  source_type?: string
  published_on?: string
  overton_url?: string
  // Tracking
  upload_step?: string
  user_feedback_ok?: boolean
  user_feedback_text?: string
  created_at: string
}

export interface AnalysisExtraction {
  id: string
  analysis_project_id: string
  analysis_document_id: string
  extraction_type: 'issue' | 'intervention' | 'mapping' | 'result' | 'conclusion'
  label?: string
  description?: string
  supporting_quote?: string
  raw_data?: Record<string, unknown>
  user_feedback_ok?: boolean
  user_feedback_text?: string
  created_at: string
}

export interface AnalysisProjectDetail extends AnalysisProject {
  documents: AnalysisDocument[]
  extractions: AnalysisExtraction[]
  document_count: number
  extraction_count: number
}

interface AnalysisProjectState {
  projects: AnalysisProject[]
  activeProject: AnalysisProject | null
  activeProjectDetail: AnalysisProjectDetail | null
  isLoading: boolean
  error: string | null
  
  // Actions
  setProjects: (projects: AnalysisProject[]) => void
  setActiveProject: (project: AnalysisProject | null) => void
  setActiveProjectDetail: (projectDetail: AnalysisProjectDetail | null) => void
  removeProject: (projectId: string) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  clearError: () => void
}

export const useAnalysisProjectStore = create<AnalysisProjectState>()(
  persist(
    (set) => ({
      projects: [],
      activeProject: null,
      activeProjectDetail: null,
      isLoading: false,
      error: null,

      setProjects: (projects) => set({ projects }),
      
      setActiveProject: (project) => set({ activeProject: project }),
      
      setActiveProjectDetail: (projectDetail) => set({ activeProjectDetail: projectDetail }),
      
      removeProject: (projectId) => set((state) => ({
        projects: state.projects.filter(p => p.id !== projectId),
        activeProject: state.activeProject?.id === projectId ? null : state.activeProject,
        activeProjectDetail: state.activeProjectDetail?.id === projectId ? null : state.activeProjectDetail
      })),
      
      setLoading: (loading) => set({ isLoading: loading }),
      
      setError: (error) => set({ error }),
      
      clearError: () => set({ error: null })
    }),
    {
      name: 'analysis-project-storage',
      partialize: (state) => ({
        activeProject: state.activeProject,
        projects: state.projects
      })
    }
  )
)
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface Project {
  id: string
  name: string
  description?: string
  evidence_count: number
  last_search_date?: string
  last_search_query?: string
  key_insights?: {
    extraction: {
      insights: Array<{
        insight: string
        confidence: number
        evidence_source: string
        supporting_quotes: string[]
      }>
      methodology?: string
      evidence_coverage?: string
    }
    review?: { approved: boolean; score: number }
    query?: string
    extracted_at?: string
    quality_score?: number
  }
  policy_recommendations?: {
    recommendations: {
      recommendations: Array<{
        recommendation: string
        rationale: string
        evidence_strength: string
        implementation_considerations: string[]
        supporting_insights: string[]
      }>
      overall_assessment?: string
      gaps_identified?: string[]
    }
    review?: { approved: boolean; score: number }
    query?: string
    generated_at?: string
    quality_score?: number
  }
  executive_brief?: {
    brief: {
      executive_summary: string
      key_findings: string[]
      policy_priorities: string[]
      evidence_strength: string
      next_steps: string[]
    }
    query?: string
    generated_at?: string
  }
  analytics?: Record<string, unknown>
  created_at: string
  updated_at: string
}

interface ProjectState {
  activeProject: Project | null
  projects: Project[]
  isLoading: boolean
  error: string | null
  
  // Actions
  setActiveProject: (project: Project | null) => void
  setProjects: (projects: Project[]) => void
  addProject: (project: Project) => void
  updateProject: (projectId: string, updates: Partial<Project>) => void
  removeProject: (projectId: string) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  clearError: () => void
}

export const useProjectStore = create<ProjectState>()(
  persist(
    (set) => ({
      activeProject: null,
      projects: [],
      isLoading: false,
      error: null,

      setActiveProject: (project) => set({ activeProject: project }),
      
      setProjects: (projects) => set({ projects }),
      
      addProject: (project) => set((state) => ({
        projects: [...state.projects, project]
      })),
      
      updateProject: (projectId, updates) => set((state) => ({
        projects: state.projects.map(p => 
          p.id === projectId ? { ...p, ...updates } : p
        ),
        activeProject: state.activeProject?.id === projectId 
          ? { ...state.activeProject, ...updates } 
          : state.activeProject
      })),
      
      removeProject: (projectId) => set((state) => ({
        projects: state.projects.filter(p => p.id !== projectId),
        activeProject: state.activeProject?.id === projectId ? null : state.activeProject
      })),
      
      setLoading: (loading) => set({ isLoading: loading }),
      
      setError: (error) => set({ error }),
      
      clearError: () => set({ error: null })
    }),
    {
      name: 'project-storage',
      partialize: (state) => ({
        activeProject: state.activeProject,
        projects: state.projects
      })
    }
  )
)
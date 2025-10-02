import { create } from 'zustand'

interface FeedbackData {
  rating: number
  comment: string
  updated_at?: string
}

interface FeedbackStore {
  feedback: Record<string, FeedbackData | null> // projectId -> feedback
  isLoading: boolean
  
  // Actions
  setFeedback: (projectId: string, feedback: FeedbackData | null) => void
  setLoading: (loading: boolean) => void
  getFeedback: (projectId: string) => FeedbackData | null
  clearFeedback: (projectId: string) => void
}

export const useFeedbackStore = create<FeedbackStore>((set, get) => ({
  feedback: {},
  isLoading: false,

  setFeedback: (projectId: string, feedback: FeedbackData | null) =>
    set((state) => ({
      feedback: {
        ...state.feedback,
        [projectId]: feedback,
      },
    })),

  setLoading: (loading: boolean) => set({ isLoading: loading }),

  getFeedback: (projectId: string) => {
    const state = get()
    return state.feedback[projectId] || null
  },

  clearFeedback: (projectId: string) =>
    set((state) => {
      const newFeedback = { ...state.feedback }
      delete newFeedback[projectId]
      return { feedback: newFeedback }
    }),
}))

// API functions
export async function fetchProjectFeedback(projectId: string): Promise<FeedbackData | null> {
  try {
    // Import the fetchWithAuthExternal function
    const { fetchWithAuthExternal } = await import('./api')
    
    const data = await fetchWithAuthExternal(`api/analysis-projects/${projectId}/feedback`)
    return data.feedback
  } catch (error: unknown) {
    console.error('Error fetching project feedback:', error)
    // If it's a 404, return null (no feedback exists)
    if (error instanceof Error && error.message?.includes('404')) {
      return null
    }
    throw error
  }
}

export async function saveProjectFeedback(
  projectId: string,
  feedback: { rating: number; comment: string }
): Promise<FeedbackData> {
  try {
    // Import the fetchWithAuthExternal function
    const { fetchWithAuthExternal } = await import('./api')
    
    const data = await fetchWithAuthExternal(`api/analysis-projects/${projectId}/feedback`, {
      method: 'POST',
      body: JSON.stringify(feedback),
    })
    
    return data.feedback
  } catch (error: unknown) {
    console.error('Error saving project feedback:', error)
    throw new Error(error instanceof Error ? error.message : 'Failed to save feedback')
  }
}
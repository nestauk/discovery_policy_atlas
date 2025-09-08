import { create } from 'zustand'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  references?: DocumentReference[]
}

export interface DocumentReference {
  document_id: string
  title: string
  authors?: string[]
  doi?: string
  url?: string
  chunk_type?: string
  published_date?: string
  year?: number
}

export interface ChatResponse {
  message: string
  references: DocumentReference[]
}

interface V2ChatState {
  messages: ChatMessage[]
  isLoading: boolean
  error: string | null
  isOpen: boolean
  
  // Actions
  addMessage: (message: ChatMessage) => void
  setMessages: (messages: ChatMessage[]) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  setIsOpen: (isOpen: boolean) => void
  clearMessages: () => void
  clearError: () => void
}

export const useV2ChatStore = create<V2ChatState>((set) => ({
  messages: [],
  isLoading: false,
  error: null,
  isOpen: false,
  
  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message]
  })),
  
  setMessages: (messages) => set({ messages }),
  
  setLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({ error }),
  
  setIsOpen: (isOpen) => set({ isOpen }),
  
  clearMessages: () => set({ messages: [] }),
  
  clearError: () => set({ error: null })
}))
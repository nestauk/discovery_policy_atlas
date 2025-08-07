import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

interface SearchResult {
  papers: Record<string, unknown>[]
  total_found: number
  total_screened: number
  total_relevant: number
}

interface ChatbotState {
  messages: Message[]
  isOpen: boolean
  researchQuestion: string
  conversationId: string | null
  conversationState: string
  searchQuery: string
  evidenceSearchReady: boolean
  outcomesDefined: boolean
  scopeDefined: boolean
  searchResults: SearchResult | null
  searchInProgress: boolean
  searchCompleted: boolean
  addMessage: (message: Message) => void
  setMessages: (messages: Message[]) => void
  setIsOpen: (isOpen: boolean) => void
  setResearchQuestion: (question: string) => void
  setConversationId: (id: string | null) => void
  setConversationState: (state: string) => void
  setSearchQuery: (query: string) => void
  setEvidenceSearchReady: (ready: boolean) => void
  setOutcomesDefined: (defined: boolean) => void
  setScopeDefined: (defined: boolean) => void
  setSearchResults: (results: SearchResult | null) => void
  setSearchInProgress: (inProgress: boolean) => void
  setSearchCompleted: (completed: boolean) => void
  clearMessages: () => void
}

export const useChatbotStore = create<ChatbotState>()(
  persist(
    (set) => ({
      messages: [],
      isOpen: false,
      researchQuestion: '',
      conversationId: null,
      conversationState: 'refine',
      searchQuery: '',
      evidenceSearchReady: false,
      outcomesDefined: false,
      scopeDefined: false,
      searchResults: null,
      searchInProgress: false,
      searchCompleted: false,
      
      addMessage: (message: Message) => {
        set((state) => ({
          messages: [...state.messages, message]
        }))
      },
      
      setMessages: (messages: Message[]) => {
        set({ messages })
      },
      
      setIsOpen: (isOpen: boolean) => {
        set({ isOpen })
      },
      
      setResearchQuestion: (question: string) => {
        set({ researchQuestion: question })
      },
      
      setConversationId: (id: string | null) => {
        set({ conversationId: id })
      },
      
      setConversationState: (state: string) => {
        set({ conversationState: state })
      },
      
      setSearchQuery: (query: string) => {
        set({ searchQuery: query })
      },
      
      setEvidenceSearchReady: (ready: boolean) => {
        set({ evidenceSearchReady: ready })
      },
      
      setOutcomesDefined: (defined: boolean) => {
        set({ outcomesDefined: defined })
      },
      
      setScopeDefined: (defined: boolean) => {
        set({ scopeDefined: defined })
      },
      
      setSearchResults: (results: SearchResult | null) => {
        set({ searchResults: results })
      },
      
      setSearchInProgress: (inProgress: boolean) => {
        set({ searchInProgress: inProgress })
      },
      
      setSearchCompleted: (completed: boolean) => {
        set({ searchCompleted: completed })
      },
      
      clearMessages: () => {
        set({ 
          messages: [], 
          conversationId: null, 
          conversationState: 'refine',
          searchQuery: '',
          evidenceSearchReady: false,
          outcomesDefined: false,
          scopeDefined: false,
          searchResults: null,
          searchInProgress: false,
          searchCompleted: false
        })
      }
    }),
    {
      name: 'chatbot-storage',
      // Only persist messages and conversation state, not UI state
      partialize: (state) => ({
        messages: state.messages,
        researchQuestion: state.researchQuestion,
        conversationId: state.conversationId,
        conversationState: state.conversationState,
        searchQuery: state.searchQuery,
        evidenceSearchReady: state.evidenceSearchReady,
        outcomesDefined: state.outcomesDefined,
        scopeDefined: state.scopeDefined,
        searchResults: state.searchResults,
        searchCompleted: state.searchCompleted
      })
    }
  )
) 
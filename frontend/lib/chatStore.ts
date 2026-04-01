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

// TODO: Add eviction (e.g. cap at N most-recent projects) to prevent
// unbounded localStorage growth across long-lived sessions.
type MessagesByProject = Record<string, ChatMessage[]>

const CHAT_MESSAGES_STORAGE_KEY = 'policy-atlas:chat-messages'
const EMPTY_MESSAGES: ChatMessage[] = []

function isLegacyChatStore(value: unknown): boolean {
  return Boolean(
    value &&
      typeof value === 'object' &&
      !Array.isArray(value) &&
      ('messages' in value || 'isLoading' in value || 'error' in value || 'isOpen' in value)
  )
}

function loadMessagesByProject(): MessagesByProject {
  if (typeof window === 'undefined') {
    return {}
  }

  try {
    const storedValue = window.localStorage.getItem(CHAT_MESSAGES_STORAGE_KEY)
    if (!storedValue) {
      return {}
    }

    const parsedValue: unknown = JSON.parse(storedValue)
    if (!parsedValue || typeof parsedValue !== 'object' || Array.isArray(parsedValue) || isLegacyChatStore(parsedValue)) {
      return {}
    }

    const parsedEntries = Object.entries(parsedValue).reduce<MessagesByProject>((acc, [projectId, messages]) => {
      if (!Array.isArray(messages)) {
        return acc
      }

      const parsedMessages = messages.flatMap((message) => {
        if (!message || typeof message !== 'object') {
          return []
        }

        const candidate = message as Partial<ChatMessage> & { timestamp?: string }
        if (
          typeof candidate.id !== 'string' ||
          (candidate.role !== 'user' && candidate.role !== 'assistant') ||
          typeof candidate.content !== 'string' ||
          typeof candidate.timestamp !== 'string'
        ) {
          return []
        }

        const timestamp = new Date(candidate.timestamp)
        if (Number.isNaN(timestamp.getTime())) {
          return []
        }

        return [{
          id: candidate.id,
          role: candidate.role,
          content: candidate.content,
          timestamp,
          references: Array.isArray(candidate.references) ? candidate.references : undefined
        }]
      })

      acc[projectId] = parsedMessages
      return acc
    }, {})

    return parsedEntries
  } catch {
    return {}
  }
}

function persistMessagesByProject(messagesByProject: MessagesByProject) {
  if (typeof window === 'undefined') {
    return
  }

  try {
    const serializedValue = Object.fromEntries(
      Object.entries(messagesByProject).map(([projectId, messages]) => [
        projectId,
        messages.map((message) => ({
          ...message,
          timestamp: message.timestamp.toISOString()
        }))
      ])
    )

    window.localStorage.setItem(CHAT_MESSAGES_STORAGE_KEY, JSON.stringify(serializedValue))
  } catch {
    // Ignore localStorage failures and keep the in-memory chat working.
  }
}

interface ChatState {
  messagesByProject: MessagesByProject
  activeProjectId: string | null
  isLoading: boolean
  error: string | null
  isOpen: boolean
  
  // Actions
  addMessage: (projectId: string, message: ChatMessage) => void
  getMessages: (projectId: string) => ChatMessage[]
  removeLastMessage: (projectId: string) => void
  setActiveProjectId: (projectId: string | null) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  setIsOpen: (isOpen: boolean) => void
  clearMessages: (projectId: string) => void
  clearError: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  messagesByProject: loadMessagesByProject(),
  activeProjectId: null,
  isLoading: false,
  error: null,
  isOpen: false,
  
  addMessage: (projectId, message) => set((state) => {
    const nextMessagesByProject = {
      ...state.messagesByProject,
      [projectId]: [...(state.messagesByProject[projectId] ?? []), message]
    }

    persistMessagesByProject(nextMessagesByProject)

    return { messagesByProject: nextMessagesByProject }
  }),

  getMessages: (projectId) => get().messagesByProject[projectId] ?? EMPTY_MESSAGES,

  removeLastMessage: (projectId) => set((state) => {
    const projectMessages = state.messagesByProject[projectId] ?? []
    const lastMessage = projectMessages[projectMessages.length - 1]

    if (!lastMessage || lastMessage.role !== 'user') {
      return state
    }

    const nextMessagesByProject = {
      ...state.messagesByProject,
      [projectId]: projectMessages.slice(0, -1)
    }

    persistMessagesByProject(nextMessagesByProject)

    return { messagesByProject: nextMessagesByProject }
  }),

  setActiveProjectId: (projectId) => set({ activeProjectId: projectId }),
  
  setLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({ error }),
  
  setIsOpen: (isOpen) => set({ isOpen }),
  
  clearMessages: (projectId) => set((state) => {
    const nextMessagesByProject = {
      ...state.messagesByProject,
      [projectId]: []
    }

    persistMessagesByProject(nextMessagesByProject)

    return { messagesByProject: nextMessagesByProject }
  }),
  
  clearError: () => set({ error: null })
}))

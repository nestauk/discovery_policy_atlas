import { create } from 'zustand'

export const SIDEBAR_MIN_WIDTH = 320
export const SIDEBAR_MAX_WIDTH = 800
export const SIDEBAR_DEFAULT_WIDTH = 400

export interface ChatStep {
  id: string
  type: 'status' | 'tool' | 'message'
  label: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  summary?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  references?: DocumentReference[]
  steps?: ChatStep[]
  isStreaming?: boolean
  activitySummary?: string
  error?: string
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
  steps?: ChatStep[]
  activity_summary?: string
}

export interface ChatStreamEvent {
  type: 'agent.status' | 'tool.started' | 'tool.completed' | 'tool.failed' | 'message.completed' | 'message.failed'
  step?: ChatStep
  message?: string
  references?: DocumentReference[]
  activity_summary?: string
  error?: string
}

export type ChatModeType = 'default' | 'forecast'

export function chatStorageKey(projectId: string, mode?: ChatModeType | null): string {
  return mode && mode !== 'default' ? `${projectId}:${mode}` : projectId
}

export interface ChatLaunchIntent {
  intentId: string
  sectionTitle: string
  contextHint: string
  prefillQuestion?: string
  mode?: ChatModeType
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
          references: Array.isArray(candidate.references) ? candidate.references : undefined,
          activitySummary: typeof (candidate as { activitySummary?: unknown }).activitySummary === 'string'
            ? (candidate as { activitySummary: string }).activitySummary
            : undefined,
          steps: Array.isArray((candidate as { steps?: unknown }).steps)
            ? (candidate as { steps: ChatStep[] }).steps
            : undefined
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
  activeMode: ChatModeType | null
  isLoading: boolean
  error: string | null
  isOpen: boolean
  chatLaunchIntent: ChatLaunchIntent | null
  sidebarWidth: number

  // Actions
  addMessage: (projectId: string, message: ChatMessage) => void
  getMessages: (projectId: string) => ChatMessage[]
  setActiveProjectId: (projectId: string | null) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  setIsOpen: (isOpen: boolean) => void
  setSidebarWidth: (width: number) => void
  clearMessages: (projectId: string) => void
  clearError: () => void
  openChatWithIntent: (intent: ChatLaunchIntent) => void
  consumeChatLaunchIntent: (intentId: string) => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  messagesByProject: loadMessagesByProject(),
  activeProjectId: null,
  activeMode: null,
  isLoading: false,
  error: null,
  isOpen: false,
  chatLaunchIntent: null,
  sidebarWidth: SIDEBAR_DEFAULT_WIDTH,
  
  addMessage: (projectId, message) => set((state) => {
    const nextMessagesByProject = {
      ...state.messagesByProject,
      [projectId]: [...(state.messagesByProject[projectId] ?? []), message]
    }

    persistMessagesByProject(nextMessagesByProject)

    return { messagesByProject: nextMessagesByProject }
  }),

  getMessages: (projectId) => get().messagesByProject[projectId] ?? EMPTY_MESSAGES,

  setActiveProjectId: (projectId) => set({ activeProjectId: projectId }),
  
  setLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({ error }),
  
  setIsOpen: (isOpen) => set({ isOpen }),

  setSidebarWidth: (width) => {
    if (!Number.isFinite(width)) return
    const clamped = Math.min(Math.max(width, SIDEBAR_MIN_WIDTH), SIDEBAR_MAX_WIDTH)
    if (clamped === get().sidebarWidth) return
    set({ sidebarWidth: clamped })
  },
  
  clearMessages: (projectId) => set((state) => {
    const nextMessagesByProject = {
      ...state.messagesByProject,
      [projectId]: []
    }

    persistMessagesByProject(nextMessagesByProject)

    return { messagesByProject: nextMessagesByProject }
  }),
  
  clearError: () => set({ error: null }),

  openChatWithIntent: (intent) => set({
    chatLaunchIntent: intent,
    isOpen: true,
    activeMode: intent.mode ?? 'default',
  }),

  consumeChatLaunchIntent: (intentId) => set((state) => (
    state.chatLaunchIntent?.intentId === intentId
      ? { chatLaunchIntent: null }
      : {}
  )),
}))

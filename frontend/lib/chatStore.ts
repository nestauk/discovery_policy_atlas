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

export interface AnswerMetadata {
  source_count: number
  evidence_source_count: number
  parliament_source_count: number
  date_range?: string
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
  answerMetadata?: AnswerMetadata
  responseId?: string
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
  type: 'agent.status' | 'tool.started' | 'tool.completed' | 'tool.failed' | 'message.completed' | 'message.failed' | 'message.delta'
  step?: ChatStep
  message?: string
  references?: DocumentReference[]
  activity_summary?: string
  answer_metadata?: AnswerMetadata
  response_id?: string
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

// ---------------------------------------------------------------------------
// Multi-conversation data model
// ---------------------------------------------------------------------------

export interface ConversationMeta {
  id: string
  title: string
  mode: ChatModeType
  createdAt: string
  updatedAt: string
  messageCount: number
}

interface ProjectChatData {
  conversations: ConversationMeta[]
  activeConversationId: string | null
}

type MetaByProject = Record<string, ProjectChatData>

const META_STORAGE_KEY = 'policy-atlas:chat-messages'
const CONV_KEY_PREFIX = 'policy-atlas:chat-conv:'
const MAX_CONVERSATIONS = 20
const MAX_MESSAGES_PER_CONVERSATION = 100
const EMPTY_MESSAGES: ChatMessage[] = []
const EMPTY_PROJECT: ProjectChatData = { conversations: [], activeConversationId: null }
const EMPTY_CONVERSATIONS: ConversationMeta[] = []

// ---------------------------------------------------------------------------
// localStorage helpers — per-conversation message storage
// ---------------------------------------------------------------------------
//
// Messages are persisted to localStorage but cached in-memory so reads (which
// happen on every render via getMessages) don't repeatedly parse JSON. The
// cache is the source of truth at runtime; localStorage is the persistence
// layer.

const messagesCache = new Map<string, ChatMessage[]>()

function convStorageKey(conversationId: string): string {
  return `${CONV_KEY_PREFIX}${conversationId}`
}

function getCachedMessages(conversationId: string): ChatMessage[] {
  const cached = messagesCache.get(conversationId)
  if (cached) return cached
  const loaded = loadConversationMessages(conversationId)
  messagesCache.set(conversationId, loaded)
  return loaded
}

function parseMessageArray(raw: unknown[]): ChatMessage[] {
  return raw.flatMap((message) => {
    if (!message || typeof message !== 'object') return []
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
    if (Number.isNaN(timestamp.getTime())) return []
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
        : undefined,
    }]
  })
}

function loadConversationMessages(conversationId: string): ChatMessage[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(convStorageKey(conversationId))
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parseMessageArray(parsed)
  } catch {
    return []
  }
}

function persistConversationMessages(conversationId: string, messages: ChatMessage[]) {
  const capped = messages.length > MAX_MESSAGES_PER_CONVERSATION
    ? messages.slice(-MAX_MESSAGES_PER_CONVERSATION)
    : messages
  messagesCache.set(conversationId, capped)
  if (typeof window === 'undefined') return
  const serialized = JSON.stringify(
    capped.map((m) => ({ ...m, timestamp: m.timestamp.toISOString() }))
  )
  try {
    window.localStorage.setItem(convStorageKey(conversationId), serialized)
  } catch {
    // QuotaExceededError — silently fail; cache still holds the latest messages
  }
}

function removeConversationMessages(conversationId: string) {
  messagesCache.delete(conversationId)
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(convStorageKey(conversationId))
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Metadata persistence (index of conversations per project+mode)
// ---------------------------------------------------------------------------

function deriveTitle(messages: ChatMessage[]): string {
  const firstUserMsg = messages.find((m) => m.role === 'user')
  if (!firstUserMsg) return 'New conversation'
  const text = firstUserMsg.content.trim()
  if (text.length <= 50) return text
  const truncated = text.substring(0, 50)
  const lastSpace = truncated.lastIndexOf(' ')
  return (lastSpace > 20 ? truncated.substring(0, lastSpace) : truncated) + '...'
}

function inferModeFromKey(key: string): ChatModeType {
  return key.endsWith(':forecast') ? 'forecast' : 'default'
}

function isLegacyChatStore(value: unknown): boolean {
  return Boolean(
    value &&
      typeof value === 'object' &&
      !Array.isArray(value) &&
      ('messages' in value || 'isLoading' in value || 'error' in value || 'isOpen' in value)
  )
}

function isNewFormatEntry(value: unknown): value is ProjectChatData {
  return Boolean(
    value &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    'conversations' in value
  )
}

function parseConversationMeta(raw: unknown): ConversationMeta | null {
  if (!raw || typeof raw !== 'object') return null
  const c = raw as Record<string, unknown>
  if (
    typeof c.id !== 'string' ||
    typeof c.title !== 'string' ||
    typeof c.createdAt !== 'string' ||
    typeof c.updatedAt !== 'string'
  ) return null
  return {
    id: c.id,
    title: c.title,
    mode: (c.mode === 'forecast' ? 'forecast' : 'default') as ChatModeType,
    createdAt: c.createdAt,
    updatedAt: c.updatedAt,
    messageCount: typeof c.messageCount === 'number' ? c.messageCount : 0,
  }
}

function loadMetaByProject(): MetaByProject {
  if (typeof window === 'undefined') return {}
  try {
    const storedValue = window.localStorage.getItem(META_STORAGE_KEY)
    if (!storedValue) return {}

    const parsedValue: unknown = JSON.parse(storedValue)
    if (!parsedValue || typeof parsedValue !== 'object' || Array.isArray(parsedValue) || isLegacyChatStore(parsedValue)) {
      return {}
    }

    const result: MetaByProject = {}

    for (const [key, value] of Object.entries(parsedValue as Record<string, unknown>)) {
      // New format — already has conversations[]
      if (isNewFormatEntry(value)) {
        const convs = Array.isArray(value.conversations)
          ? (value.conversations as unknown[]).flatMap((c) => {
              const parsed = parseConversationMeta(c)
              return parsed ? [parsed] : []
            })
          : []
        result[key] = {
          conversations: convs,
          activeConversationId: typeof value.activeConversationId === 'string'
            ? value.activeConversationId
            : (convs.length > 0 ? convs[convs.length - 1].id : null),
        }
        continue
      }

      // Old format — bare ChatMessage[] array → migrate
      if (Array.isArray(value)) {
        const messages = parseMessageArray(value)
        if (messages.length === 0) {
          result[key] = { conversations: [], activeConversationId: null }
          continue
        }

        const convId = crypto.randomUUID()
        const mode = inferModeFromKey(key)
        const meta: ConversationMeta = {
          id: convId,
          title: deriveTitle(messages),
          mode,
          createdAt: messages[0].timestamp.toISOString(),
          updatedAt: messages[messages.length - 1].timestamp.toISOString(),
          messageCount: messages.length,
        }
        persistConversationMessages(convId, messages)
        result[key] = { conversations: [meta], activeConversationId: convId }
        continue
      }
    }

    // Persist migrated metadata so next load uses new format
    persistMetaByProject(result)
    return result
  } catch {
    return {}
  }
}

function persistMetaByProject(meta: MetaByProject) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(META_STORAGE_KEY, JSON.stringify(meta))
  } catch {
    // ignore quota errors
  }
}

// ---------------------------------------------------------------------------
// Zustand store
// ---------------------------------------------------------------------------

function getProjectData(meta: MetaByProject, key: string): ProjectChatData {
  return meta[key] ?? EMPTY_PROJECT
}

interface ChatState {
  metaByProject: MetaByProject
  activeProjectId: string | null
  activeMode: ChatModeType | null
  isLoading: boolean
  error: string | null
  isOpen: boolean
  chatLaunchIntent: ChatLaunchIntent | null
  sidebarWidth: number
  /** In-memory draft conversation id — not yet persisted to conversations[] */
  draftConversationId: string | null

  // Message actions
  addMessage: (key: string, message: ChatMessage) => void
  getMessages: (key: string) => ChatMessage[]

  // Conversation actions
  getConversations: (key: string) => ConversationMeta[]
  getActiveConversationId: (key: string) => string | null
  startNewConversation: (key: string) => string
  switchConversation: (key: string, conversationId: string) => void
  deleteConversation: (key: string, conversationId: string) => void

  // UI actions
  setActiveProjectId: (projectId: string | null) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  setIsOpen: (isOpen: boolean) => void
  setSidebarWidth: (width: number) => void
  clearError: () => void
  openChatWithIntent: (intent: ChatLaunchIntent) => void
  consumeChatLaunchIntent: (intentId: string) => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  metaByProject: loadMetaByProject(),
  activeProjectId: null,
  activeMode: null,
  isLoading: false,
  error: null,
  isOpen: false,
  chatLaunchIntent: null,
  sidebarWidth: SIDEBAR_DEFAULT_WIDTH,
  draftConversationId: null,

  // ---------------------------------------------------------------------------
  // Message actions
  // ---------------------------------------------------------------------------

  getMessages: (key) => {
    const state = get()
    const project = getProjectData(state.metaByProject, key)
    const activeId = state.draftConversationId ?? project.activeConversationId
    if (!activeId) return EMPTY_MESSAGES
    return getCachedMessages(activeId)
  },

  addMessage: (key, message) => set((state) => {
    const project = { ...getProjectData(state.metaByProject, key) }
    let conversationId = state.draftConversationId ?? project.activeConversationId
    let nextDraft = state.draftConversationId
    const mode = inferModeFromKey(key)

    // If no active conversation, auto-create one
    if (!conversationId) {
      conversationId = crypto.randomUUID()
      nextDraft = conversationId
    }

    // Append to existing messages (cache-first; persist write-through)
    const existingMessages = getCachedMessages(conversationId)
    const updatedMessages = [...existingMessages, message]
    persistConversationMessages(conversationId, updatedMessages)

    // If this is a draft (not yet in conversations[]), materialize it on first user message
    if (nextDraft === conversationId && message.role === 'user') {
      const now = new Date().toISOString()
      const meta: ConversationMeta = {
        id: conversationId,
        title: deriveTitle(updatedMessages),
        mode,
        createdAt: now,
        updatedAt: now,
        messageCount: updatedMessages.length,
      }
      const conversations = [...project.conversations]
      if (conversations.length >= MAX_CONVERSATIONS) {
        const evicted = conversations.shift()
        if (evicted) removeConversationMessages(evicted.id)
      }
      conversations.push(meta)
      project.conversations = conversations
      project.activeConversationId = conversationId
      nextDraft = null
    } else {
      project.conversations = project.conversations.map((c) =>
        c.id === conversationId
          ? { ...c, updatedAt: new Date().toISOString(), messageCount: updatedMessages.length }
          : c
      )
    }

    const nextMeta = { ...state.metaByProject, [key]: project }
    persistMetaByProject(nextMeta)
    return { metaByProject: nextMeta, draftConversationId: nextDraft }
  }),

  // ---------------------------------------------------------------------------
  // Conversation actions
  // ---------------------------------------------------------------------------

  getConversations: (key) => {
    const project = getProjectData(get().metaByProject, key)
    return project.conversations.length > 0 ? project.conversations : EMPTY_CONVERSATIONS
  },

  getActiveConversationId: (key) => {
    const state = get()
    if (state.draftConversationId) return state.draftConversationId
    return getProjectData(state.metaByProject, key).activeConversationId
  },

  startNewConversation: (key) => {
    const newId = crypto.randomUUID()
    const state = get()
    const project = { ...getProjectData(state.metaByProject, key) }
    project.activeConversationId = newId
    const nextMeta = { ...state.metaByProject, [key]: project }
    persistMetaByProject(nextMeta)
    set({
      metaByProject: nextMeta,
      draftConversationId: newId,
      activeMode: inferModeFromKey(key),
    })
    return newId
  },

  switchConversation: (key, conversationId) => set((state) => {
    const project = { ...getProjectData(state.metaByProject, key) }
    project.activeConversationId = conversationId
    const nextMeta = { ...state.metaByProject, [key]: project }
    persistMetaByProject(nextMeta)
    return { metaByProject: nextMeta, draftConversationId: null }
  }),

  deleteConversation: (key, conversationId) => set((state) => {
    const project = { ...getProjectData(state.metaByProject, key) }
    project.conversations = project.conversations.filter((c) => c.id !== conversationId)
    removeConversationMessages(conversationId)

    if (project.activeConversationId === conversationId) {
      const remaining = project.conversations
      project.activeConversationId = remaining.length > 0
        ? remaining[remaining.length - 1].id
        : null
    }

    const nextMeta = { ...state.metaByProject, [key]: project }
    persistMetaByProject(nextMeta)
    return {
      metaByProject: nextMeta,
      draftConversationId: state.draftConversationId === conversationId
        ? null
        : state.draftConversationId,
    }
  }),

  // ---------------------------------------------------------------------------
  // UI actions
  // ---------------------------------------------------------------------------

  setActiveProjectId: (projectId) => set({ activeProjectId: projectId }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  setIsOpen: (isOpen) => set(isOpen
    ? { isOpen }
    : { isOpen, activeMode: 'default', chatLaunchIntent: null }
  ),

  setSidebarWidth: (width) => {
    if (!Number.isFinite(width)) return
    const clamped = Math.min(Math.max(width, SIDEBAR_MIN_WIDTH), SIDEBAR_MAX_WIDTH)
    if (clamped === get().sidebarWidth) return
    set({ sidebarWidth: clamped })
  },

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

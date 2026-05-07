'use client'

import { useState } from 'react'
import { Plus, Trash2, MessageSquare } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useChatStore, ConversationMeta } from '@/lib/chatStore'

function formatRelativeTime(isoString: string): string {
  const now = Date.now()
  const then = new Date(isoString).getTime()
  const diffMs = now - then
  const diffMins = Math.floor(diffMs / 60_000)
  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  return new Date(isoString).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

interface ChatHistoryListProps {
  chatKey: string
  onClose: () => void
}

export function ChatHistoryList({ chatKey, onClose }: ChatHistoryListProps) {
  const {
    getConversations,
    getActiveConversationId,
    startNewConversation,
    switchConversation,
    deleteConversation,
    draftConversationId,
  } = useChatStore()

  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  const conversations = getConversations(chatKey)
  const activeId = getActiveConversationId(chatKey)

  const handleNewConversation = () => {
    startNewConversation(chatKey)
    onClose()
  }

  const handleSelect = (conv: ConversationMeta) => {
    switchConversation(chatKey, conv.id)
    onClose()
  }

  const handleDelete = (convId: string) => {
    deleteConversation(chatKey, convId)
    setConfirmDeleteId(null)
  }

  const sorted = [...conversations].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
  )

  const hasDraft = Boolean(draftConversationId && !conversations.some((c) => c.id === draftConversationId))

  return (
    <div className="flex flex-col max-h-64">
      {/* Header row */}
      <div className="flex items-center justify-between px-3 py-2">
        <span className="text-[11px] font-medium text-gray-500 uppercase tracking-wide">Conversations</span>
        <button
          type="button"
          onClick={handleNewConversation}
          className="flex items-center gap-1 text-[11px] font-medium text-blue-600 hover:text-blue-700 transition-colors"
        >
          <Plus className="h-3 w-3" />
          New
        </button>
      </div>

      {sorted.length === 0 && !hasDraft && (
        <div className="px-3 pb-3 text-xs text-gray-400 text-center">
          No conversations yet
        </div>
      )}

      {/* Conversation list */}
      <div className="overflow-y-auto">
        {hasDraft && (
          <div className="flex items-center gap-2.5 mx-2 mb-1 px-2.5 py-2 rounded-md bg-blue-100/60">
            <MessageSquare className="h-3.5 w-3.5 text-blue-500 shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="text-xs font-medium text-blue-700 truncate">New conversation</div>
              <div className="text-[10px] text-blue-500">Draft</div>
            </div>
          </div>
        )}

        {sorted.map((conv) => {
          const isActive = conv.id === activeId && !hasDraft
          const isConfirming = confirmDeleteId === conv.id

          return (
            <div
              key={conv.id}
              className={`group flex items-center gap-2.5 mx-2 mb-1 last:mb-2 px-2.5 py-2 rounded-md transition-colors ${
                isActive
                  ? 'bg-white shadow-sm ring-1 ring-gray-200'
                  : 'hover:bg-white/60'
              }`}
            >
              <button
                type="button"
                onClick={() => handleSelect(conv)}
                className="min-w-0 flex-1 text-left"
              >
                <div className={`text-xs font-medium truncate ${isActive ? 'text-gray-900' : 'text-gray-700'}`}>
                  {conv.title}
                </div>
                <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-gray-400">
                  <span>{formatRelativeTime(conv.updatedAt)}</span>
                  <span className="text-gray-300">&middot;</span>
                  <span>{conv.messageCount} msg{conv.messageCount !== 1 ? 's' : ''}</span>
                </div>
              </button>

              {isConfirming ? (
                <div className="flex items-center gap-1 shrink-0">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(conv.id)}
                    className="h-6 px-1.5 text-[10px] text-red-600 hover:bg-red-50 hover:text-red-700"
                  >
                    Delete
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setConfirmDeleteId(null)}
                    className="h-6 px-1.5 text-[10px] text-gray-500 hover:bg-gray-100"
                  >
                    Cancel
                  </Button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    setConfirmDeleteId(conv.id)
                  }}
                  className="shrink-0 p-1 rounded opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all"
                  aria-label={`Delete conversation: ${conv.title}`}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

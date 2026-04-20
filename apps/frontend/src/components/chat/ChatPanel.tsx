import { useCallback, useEffect, useLayoutEffect, useRef } from 'react'

import { MessageRow } from '@/components/chat/MessageRow'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { ChatMessage } from '@/types'

interface ChatPanelProps {
  messages: ChatMessage[]
  isSending: boolean
  selectedAgent: string
  runtimeReady: boolean
  onSendMessage: (text: string, options?: { from_widget?: string }) => void
  onSendFollowUp: (chip: string, messageId: string) => void
}

const SVG_SUGGESTIONS = [
  'Pick the best SVG template for a 4-step process',
  'Preserve all group ids while filling this SVG',
  'Validate this SVG for alignment and identity drift',
]

const DEFAULT_SUGGESTIONS = [
  'Explain gradient descent visually',
  'Compare stack vs queue',
  'Compare dense vs MoE visually',
]

export function ChatPanel({
  messages,
  isSending,
  selectedAgent,
  runtimeReady,
  onSendMessage,
  onSendFollowUp,
}: ChatPanelProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const stickToBottomRef = useRef(true)
  const lastMessageCountRef = useRef(0)
  const lastMessagesRef = useRef<ChatMessage[]>([])

  const updateStickiness = useCallback(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    const distanceFromBottom =
      viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop
    stickToBottomRef.current = distanceFromBottom < 140
  }, [])

  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    viewport.addEventListener('scroll', updateStickiness, { passive: true })
    return () => viewport.removeEventListener('scroll', updateStickiness)
  }, [updateStickiness])

  // Streaming-friendly scroll: auto during streaming, smooth only when turn completes
  useLayoutEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return

    const previous = lastMessagesRef.current
    lastMessagesRef.current = messages

    const isNewMessage = messages.length > lastMessageCountRef.current
    lastMessageCountRef.current = messages.length

    // When a new message is appended (e.g. user just sent one), pin to bottom
    if (isNewMessage) {
      stickToBottomRef.current = true
    }

    if (!stickToBottomRef.current) {
      return
    }

    // Detect if a turn just completed (any assistant message's isStreaming flipped to false)
    let turnJustCompleted = false
    for (let i = 0; i < messages.length; i += 1) {
      const current = messages[i]
      const prev = previous[i]
      if (
        current?.role === 'assistant' &&
        prev?.role === 'assistant' &&
        prev.isStreaming &&
        !current.isStreaming
      ) {
        turnJustCompleted = true
        break
      }
    }

    viewport.scrollTo({
      top: viewport.scrollHeight,
      behavior: turnJustCompleted ? 'smooth' : 'auto',
    })
  }, [messages])

  const suggestions = selectedAgent === 'svg' ? SVG_SUGGESTIONS : DEFAULT_SUGGESTIONS

  return (
    <div
      ref={viewportRef}
      className={cn(
        'flex-1 overflow-y-auto scrollbar-thin',
        'flex flex-col gap-6 px-4 py-6 md:px-8 md:py-8',
      )}
    >
      {messages.length === 0 ? (
        <div className="mx-auto flex w-full max-w-2xl flex-col items-center gap-6 py-12 text-center">
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">
              {selectedAgent === 'svg'
                ? 'Template, instance, or brand-safe edit?'
                : 'What should we visualize?'}
            </h2>
            <p className="text-sm text-muted-foreground">
              {selectedAgent === 'svg'
                ? 'Start with a template selection, slot mapping, validation, or brand-safe SVG edit.'
                : 'Pick a concept, mechanism, or comparison — the agent reasons, answers, and finalizes a diagram.'}
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            {suggestions.map((suggestion) => (
              <Button
                key={suggestion}
                variant="outline"
                size="sm"
                className="rounded-full"
                disabled={!runtimeReady || isSending}
                onClick={() => onSendMessage(suggestion)}
              >
                {suggestion}
              </Button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        {messages.map((message) => (
          <MessageRow
            key={message.id}
            message={message}
            isSending={isSending}
            onSendMessage={onSendMessage}
            onSendFollowUp={onSendFollowUp}
          />
        ))}
      </div>
    </div>
  )
}

import { Bot, User } from 'lucide-react'

import { AssistantText } from '@/components/chat/AssistantText'
import { ReasoningCard } from '@/components/chat/ReasoningCard'
import { StatusPill } from '@/components/chat/StatusPill'
import { LoadingCard, WidgetErrorCard } from '@/components/chat/WidgetShell'
import { WidgetFrame } from '@/components/WidgetFrame'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { AssistantMessage, ChatMessage } from '@/types'

interface MessageRowProps {
  message: ChatMessage
  isSending: boolean
  onSendMessage: (text: string, options?: { from_widget?: string }) => void
  onSendFollowUp: (chip: string, messageId: string) => void
}

function Avatar({ tone }: { tone: 'user' | 'assistant' }) {
  const isUser = tone === 'user'
  return (
    <div
      className={cn(
        'flex size-8 shrink-0 items-center justify-center rounded-full border',
        isUser
          ? 'border-border bg-muted text-foreground'
          : 'border-primary/30 bg-primary/10 text-primary',
      )}
    >
      {isUser ? <User className="size-4" /> : <Bot className="size-4" />}
    </div>
  )
}

function UserMessageRow({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="flex max-w-[85%] items-start gap-3 md:max-w-[75%]">
        <div className="min-w-0 rounded-2xl rounded-tr-md border border-border/60 bg-muted/60 px-4 py-2.5 text-sm leading-relaxed text-foreground">
          <div className="whitespace-pre-wrap break-words">{text}</div>
        </div>
        <Avatar tone="user" />
      </div>
    </div>
  )
}

function getLatestWidgetTitle(message: AssistantMessage): string | null {
  for (let i = message.widgets.length - 1; i >= 0; i -= 1) {
    const widgetState = message.widgets[i]
    if (widgetState?.widget !== null) {
      return widgetState.widget.title
    }
  }
  return null
}

function AssistantMessageRow({
  message,
  isSending,
  onSendMessage,
  onSendFollowUp,
}: {
  message: AssistantMessage
  isSending: boolean
  onSendMessage: (text: string, options?: { from_widget?: string }) => void
  onSendFollowUp: (chip: string, messageId: string) => void
}) {
  const hasContent =
    message.answerText.length > 0 ||
    message.widgets.length > 0 ||
    message.thinkingText.length > 0
  const showReasoningNote =
    !message.isStreaming && !message.thinkingText && message.answerText.length > 0

  const latestWidgetTitle = getLatestWidgetTitle(message)

  return (
    <div className="flex items-start gap-3">
      <Avatar tone="assistant" />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        {message.status ? <StatusPill status={message.status} /> : null}

        {message.thinkingText ? (
          <ReasoningCard text={message.thinkingText} isStreaming={message.isStreaming} />
        ) : null}
        {showReasoningNote ? (
          <div className="text-xs text-muted-foreground/80">
            This model did not return visible reasoning tokens for this turn.
          </div>
        ) : null}

        {message.answerText ? (
          <AssistantText text={message.answerText} isStreaming={message.isStreaming} />
        ) : null}

        {message.widgets.length > 0 ? (
          <section className="flex flex-col gap-2" aria-label="Final visuals">
            <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              Visuals
            </div>
            <div className="flex flex-col gap-3">
              {message.widgets.map((widgetState) => (
                <div
                  key={widgetState.id}
                  className="overflow-hidden rounded-xl border border-border bg-card"
                >
                  {widgetState.widget ? (
                    <WidgetFrame
                      widget={widgetState.widget}
                      onPrompt={(text) =>
                        onSendMessage(text, { from_widget: widgetState.widget!.title })
                      }
                    />
                  ) : widgetState.errorMessage ? (
                    <WidgetErrorCard message={widgetState.errorMessage} />
                  ) : (
                    <LoadingCard
                      key={widgetState.loadingMessages.join('|')}
                      messages={widgetState.loadingMessages}
                    />
                  )}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {!message.isStreaming && message.followUp?.chips.length ? (
          <div
            className="flex flex-wrap gap-2 pt-1"
            aria-label="Follow-up suggestions"
          >
            {message.followUp.chips.map((chip) => (
              <Button
                key={chip}
                variant="outline"
                size="sm"
                className="rounded-full"
                disabled={isSending}
                onClick={() => onSendFollowUp(chip, message.id)}
                data-widget-context={latestWidgetTitle ?? undefined}
              >
                {chip}
              </Button>
            ))}
          </div>
        ) : null}

        {!hasContent && !message.status ? (
          <div className="h-5" aria-hidden="true" />
        ) : null}
      </div>
    </div>
  )
}

export function MessageRow({
  message,
  isSending,
  onSendMessage,
  onSendFollowUp,
}: MessageRowProps) {
  if (message.role === 'user') {
    return <UserMessageRow text={message.text} />
  }
  return (
    <AssistantMessageRow
      message={message}
      isSending={isSending}
      onSendMessage={onSendMessage}
      onSendFollowUp={onSendFollowUp}
    />
  )
}

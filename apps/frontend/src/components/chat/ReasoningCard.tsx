import { ChevronDown, Sparkles } from 'lucide-react'
import { useState } from 'react'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

interface ReasoningCardProps {
  text: string
  isStreaming: boolean
}

export function ReasoningCard({ text, isStreaming }: ReasoningCardProps) {
  const [isOpenWhileStreaming, setIsOpenWhileStreaming] = useState(true)
  const [isOpenAfterStream, setIsOpenAfterStream] = useState(false)
  const tokenEstimate = Math.max(1, Math.round(text.length / 4))

  const open = isStreaming ? isOpenWhileStreaming : isOpenAfterStream

  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => {
        if (isStreaming) {
          setIsOpenWhileStreaming(next)
          // Carry the explicit choice past the end of the stream so a card the
          // user re-opened keeps its state when streaming finishes.
          setIsOpenAfterStream(next)
        } else {
          setIsOpenAfterStream(next)
        }
      }}
      className="rounded-xl border border-border/60 bg-muted/40"
    >
      <CollapsibleTrigger
        className={cn(
          'group flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-xs font-medium text-muted-foreground transition-colors hover:text-foreground',
        )}
      >
        <span className="inline-flex items-center gap-2">
          <Sparkles className="size-3.5 opacity-70" />
          Reasoning
        </span>
        <span className="inline-flex items-center gap-2">
          <span>{isStreaming ? 'streaming…' : `${tokenEstimate} thinking tokens`}</span>
          <ChevronDown
            className={cn(
              'size-3.5 transition-transform duration-200',
              open && 'rotate-180',
            )}
          />
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
        <div className="whitespace-pre-wrap border-t border-border/50 px-4 py-3 text-[13px] leading-6 text-muted-foreground">
          {text}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

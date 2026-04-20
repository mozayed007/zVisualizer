import { ArrowUp, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useRef } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface ComposerProps {
  value: string
  onChange: (next: string) => void
  onSubmit: () => void
  disabled: boolean
  isSending: boolean
  placeholder: string
  error?: string | null
}

const MIN_ROWS_PX = 52
const MAX_ROWS_PX = 280

export function Composer({
  value,
  onChange,
  onSubmit,
  disabled,
  isSending,
  placeholder,
  error,
}: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const resize = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const next = Math.min(MAX_ROWS_PX, Math.max(MIN_ROWS_PX, el.scrollHeight))
    el.style.height = `${next}px`
  }, [])

  useEffect(() => {
    resize()
  }, [value, resize])

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (!disabled && value.trim().length > 0) {
        onSubmit()
      }
    }
  }

  return (
    <form
      className="mx-auto flex w-full max-w-3xl flex-col gap-2 px-4 pb-4 md:px-8 md:pb-6"
      onSubmit={(event) => {
        event.preventDefault()
        if (!disabled && value.trim().length > 0) {
          onSubmit()
        }
      }}
    >
      <div
        className={cn(
          'relative flex items-end gap-2 rounded-2xl border border-border bg-card/80 px-3 py-2.5 shadow-sm backdrop-blur transition-colors',
          'focus-within:border-ring/60 focus-within:ring-2 focus-within:ring-ring/30',
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          disabled={disabled}
          className={cn(
            'scrollbar-thin flex-1 resize-none bg-transparent px-1 py-1 text-[0.95rem] leading-6 text-foreground outline-none placeholder:text-muted-foreground/70',
            'disabled:cursor-not-allowed disabled:opacity-60',
          )}
          style={{ minHeight: MIN_ROWS_PX, maxHeight: MAX_ROWS_PX }}
        />
        <Button
          type="submit"
          size="icon"
          variant="default"
          disabled={disabled || value.trim().length === 0}
          aria-label={isSending ? 'Sending…' : 'Send message'}
          className="rounded-full"
        >
          {isSending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <ArrowUp className="size-4" />
          )}
        </Button>
      </div>
      <div className="flex items-center justify-between gap-3 px-1">
        {error ? (
          <p className="text-xs text-destructive">{error}</p>
        ) : (
          <p className="text-xs text-muted-foreground">
            Press <kbd className="rounded border border-border bg-muted px-1 py-0.5 text-[10px]">Enter</kbd>{' '}
            to send ·{' '}
            <kbd className="rounded border border-border bg-muted px-1 py-0.5 text-[10px]">
              Shift + Enter
            </kbd>{' '}
            for newline · Visuals render in a sandboxed iframe.
          </p>
        )}
      </div>
    </form>
  )
}

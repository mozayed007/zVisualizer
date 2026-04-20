import { AlertTriangle, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'

interface LoadingCardProps {
  messages: string[]
}

export function LoadingCard({ messages }: LoadingCardProps) {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (messages.length <= 1) {
      return
    }
    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1) % messages.length)
    }, 1800)
    return () => window.clearInterval(timer)
  }, [messages])

  return (
    <div
      className="flex min-h-[140px] items-center gap-4 rounded-xl border border-border bg-card/60 px-5 py-4"
      role="status"
      aria-live="polite"
      aria-label="Visual loading"
    >
      <Loader2 className="size-6 shrink-0 text-primary animate-spin" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-foreground">Building the visualization</div>
        <div className="truncate text-sm text-muted-foreground">{messages[index]}</div>
      </div>
    </div>
  )
}

interface WidgetErrorCardProps {
  message: string
}

export function WidgetErrorCard({ message }: WidgetErrorCardProps) {
  return (
    <div
      className="flex min-h-[120px] items-start gap-3 rounded-xl border border-destructive/40 bg-destructive/5 px-5 py-4"
      role="status"
      aria-live="polite"
    >
      <AlertTriangle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-foreground">Visual unavailable</div>
        <div className="mt-0.5 text-sm text-muted-foreground">{message}</div>
      </div>
    </div>
  )
}

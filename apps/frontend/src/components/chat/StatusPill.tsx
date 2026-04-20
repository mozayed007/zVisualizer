import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { AgentStatus } from '@/types'

interface StatusPillProps {
  status: AgentStatus
}

export function StatusPill({ status }: StatusPillProps) {
  const isActive = status.state === 'active'
  const isError = status.state === 'error'
  const isDone = status.state === 'completed'

  const Icon = isError ? AlertTriangle : isDone ? CheckCircle2 : Loader2

  return (
    <div
      className={cn(
        'flex items-start gap-2.5 rounded-xl border px-3 py-2 text-sm',
        isActive && 'border-primary/30 bg-primary/5 text-foreground',
        isError && 'border-destructive/40 bg-destructive/10 text-foreground',
        isDone && 'border-emerald-500/30 bg-emerald-500/10 text-foreground',
      )}
    >
      <Icon
        className={cn(
          'mt-0.5 size-4 shrink-0',
          isActive && 'text-primary animate-spin',
          isError && 'text-destructive',
          isDone && 'text-emerald-500',
        )}
      />
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {status.label}
        </div>
        <div className="mt-0.5 text-sm leading-snug text-foreground/90">{status.detail}</div>
      </div>
    </div>
  )
}

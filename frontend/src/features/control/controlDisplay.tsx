import { AlertTriangle, CheckCircle2, Minus, XCircle } from 'lucide-react'

import type { BadgeTone } from '@/components/ui/Badge'
import type { ControlComponent, ControlLevel, ControlStatus } from '@/types/control'
import { cn } from '@/utils/cn'

/**
 * Display-only mappings for the backend's Control statuses/levels — the
 * page never derives a status or threshold itself (see services.control).
 */
export const CONTROL_STATUS_TONE: Record<ControlStatus, BadgeTone> = {
  ok: 'success',
  attention: 'warning',
  not_filled: 'danger',
  no_data: 'muted',
  upcoming: 'info',
  cancelled: 'muted',
}

const LEVEL_ICON = {
  ok: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
  none: Minus,
} as const

const LEVEL_TEXT: Record<ControlLevel, string> = {
  ok: 'text-brand-600',
  warning: 'text-warning',
  danger: 'text-danger',
  none: 'text-ink-muted',
}

const LEVEL_LABEL: Record<ControlLevel, string> = {
  ok: 'заполнено',
  warning: 'есть пропуски',
  danger: 'не заполнено',
  none: 'не требуется',
}

export function LevelIcon({ level, className }: { level: ControlLevel; className?: string }) {
  const Icon = LEVEL_ICON[level]
  return <Icon className={cn('size-4 shrink-0', LEVEL_TEXT[level], className)} aria-hidden />
}

/** `✅ 8/8` / `⚠️ 6/8` / `❌ 2/5` / `—` — one table cell of the Control page. */
export function ComponentCell({ component }: { component: ControlComponent }) {
  if (component.total === 0) {
    return (
      <span className="inline-flex items-center gap-1.5 text-ink-muted" title="За период не требуется">
        <LevelIcon level="none" />—
      </span>
    )
  }
  return (
    <span
      className={cn('inline-flex items-center gap-1.5 font-medium tabular-nums', LEVEL_TEXT[component.level])}
      title={`${component.completed} из ${component.total} — ${LEVEL_LABEL[component.level]}`}
    >
      <LevelIcon level={component.level} />
      {component.completed}/{component.total}
    </span>
  )
}

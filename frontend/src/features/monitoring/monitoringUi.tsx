import { format, parseISO } from 'date-fns'

import { Badge, type BadgeTone } from '@/components/ui/Badge'
import type { AttemptStatus, Severity } from '@/types/monitoring'

export const STATUS_LABEL: Record<AttemptStatus, string> = {
  in_progress: 'Проходит',
  completed: 'Завершён',
  expired: 'Время истекло',
  terminated: 'Прерван',
}
const STATUS_TONE: Record<AttemptStatus, BadgeTone> = {
  in_progress: 'info',
  completed: 'success',
  expired: 'muted',
  terminated: 'danger',
}
export const SEVERITY_LABEL: Record<Severity, string> = { normal: 'Норма', warning: 'Внимание', critical: 'Критично' }
const SEVERITY_TONE: Record<Severity, BadgeTone> = { normal: 'muted', warning: 'warning', critical: 'danger' }

export const VIOLATION_LABEL: Record<string, string> = {
  TAB_SWITCH: 'Уходы со страницы',
  FULLSCREEN_EXIT: 'Выходы из полноэкранного режима',
  COPY_ATTEMPT: 'Попытки копирования',
  PASTE_ATTEMPT: 'Попытки вставки',
  CUT_ATTEMPT: 'Попытки вырезания',
  CONTEXT_MENU_ATTEMPT: 'Контекстное меню',
  DEVTOOLS_ATTEMPT: 'DevTools',
  PAGE_LEAVE: 'Закрытие страницы',
}

export function StatusBadge({ status }: { status: AttemptStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge tone={SEVERITY_TONE[severity]}>{SEVERITY_LABEL[severity]}</Badge>
}

export function formatTime(value: string | null): string {
  return value ? format(parseISO(value), 'dd.MM HH:mm') : '—'
}

export function formatSeconds(value: string): string {
  return format(parseISO(value), 'HH:mm:ss')
}

export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${value}%`
}

import { format, parseISO } from 'date-fns'

/** `2026-09-30T13:42:00+06:00` → `30.09.2026 13:42`; `—` when unknown. */
export function formatDateTime(value: string | null): string {
  return value ? format(parseISO(value), 'dd.MM.yyyy HH:mm') : '—'
}

import type { ReactNode } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import type { ApplicationStatus, HRActivity, InterviewStatus, VacancyStatus } from '@/types/hr'
import { formatDateShort } from '@/utils/format'

/** Время из HR API приходит во времени офиса с поясом
 * (`2026-10-22T15:00:00+06:00`): дату и часы берём из строки, а не из пояса
 * браузера, — так время одинаковое на любом устройстве. */
export function officeDate(iso: string): string {
  return iso.slice(0, 10)
}

export function officeTime(iso: string): string {
  return iso.slice(11, 16)
}

export function officeDateTime(iso: string): string {
  return `${formatDateShort(officeDate(iso))} ${officeTime(iso)}`
}

/** Значение для `<input type="datetime-local">` и для API (без пояса — сервер
 * толкует его во времени офиса). */
export function toLocalInput(iso: string): string {
  return iso.slice(0, 16)
}

export function minutesOfDay(iso: string): number {
  return Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16))
}

export const APPLICATION_TONE: Record<ApplicationStatus, BadgeTone> = {
  new: 'info',
  screening: 'info',
  shortlisted: 'info',
  interview_scheduled: 'brand',
  interview_done: 'brand',
  awaiting_decision: 'warning',
  next_stage: 'brand',
  offer: 'warning',
  hired: 'success',
  rejected: 'danger',
  withdrawn: 'muted',
}

export const INTERVIEW_TONE: Record<InterviewStatus, BadgeTone> = {
  scheduled: 'success',
  completed: 'info',
  rescheduled: 'muted',
  cancelled: 'muted',
  no_show: 'danger',
}

export const VACANCY_TONE: Record<VacancyStatus, BadgeTone> = {
  draft: 'muted',
  published: 'success',
  paused: 'warning',
  closed: 'danger',
  archived: 'muted',
}

export function ApplicationStatusBadge({ status, label }: { status: ApplicationStatus; label: string }) {
  return <Badge tone={APPLICATION_TONE[status]}>{label}</Badge>
}

/** Размер файла по-человечески: 1,2 МБ, 340 КБ. */
export function fileSize(bytes: number | null): string {
  if (!bytes) return ''
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} МБ`
  return `${Math.max(1, Math.round(bytes / 1024))} КБ`
}

/** Ссылка на карточку кандидата с выбранным откликом. */
export function candidatePath(candidate: number, application?: number | null): string {
  return application ? `/hr/candidates/${candidate}?application=${application}` : `/hr/candidates/${candidate}`
}

export function Field({ id, label, required, hint, children }: { id: string; label: string; required?: boolean; hint?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block field-label">
        {label}
        {required ? ' *' : ''}
      </label>
      {children}
      {hint ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
    </div>
  )
}

export function FormError({ message }: { message: string | null }) {
  return message ? <p className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{message}</p> : null
}

export function FormActions({ onCancel, isLoading, submitLabel = 'Сохранить' }: { onCancel: () => void; isLoading: boolean; submitLabel?: string }) {
  return (
    <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
      <Button type="button" variant="ghost" onClick={onCancel}>Отмена</Button>
      <Button type="submit" isLoading={isLoading}>{submitLabel}</Button>
    </div>
  )
}

/** Заголовок колонки с серверной сортировкой (`ordering`): по клику —
 * по возрастанию, повторно — по убыванию. */
export function SortableTh({ label, field, ordering, onChange, className }: { label: string; field: string; ordering: string; onChange: (value: string) => void; className?: string }) {
  const active = ordering === field || ordering === `-${field}`
  const desc = ordering === `-${field}`
  const Icon = !active ? ArrowUpDown : desc ? ArrowDown : ArrowUp
  return (
    <th scope="col" className={className ?? 'px-4 py-3'} aria-sort={active ? (desc ? 'descending' : 'ascending') : undefined}>
      <button type="button" onClick={() => onChange(active && !desc ? `-${field}` : field)} className="inline-flex items-center gap-1 uppercase hover:text-ink">
        {label}
        <Icon className="size-3.5" aria-hidden />
      </button>
    </th>
  )
}

export function Th({ children, className }: { children: ReactNode; className?: string }) {
  return <th scope="col" className={className ?? 'px-4 py-3'}>{children}</th>
}

export const TABLE_HEAD = 'bg-surface-muted text-left text-xs uppercase tracking-wide text-ink-muted'

/** Лента кадровых событий (главная, карточки кандидата и сотрудника). */
export function ActivityList({ items, showSubject = true, empty = 'Событий пока нет.' }: { items: HRActivity[]; showSubject?: boolean; empty?: string }) {
  if (!items.length) return <p className="text-sm text-ink-secondary">{empty}</p>
  return (
    <ol className="space-y-3">
      {items.map((item) => (
        <li key={item.id} className="border-l-2 border-border pl-3">
          <p className="text-sm font-medium text-ink">{item.kind_label}</p>
          {item.message ? <p className="whitespace-pre-line break-words text-sm text-ink-secondary">{item.message}</p> : null}
          <p className="text-xs text-ink-muted">
            {officeDateTime(item.created_at)}
            {item.actor ? ` · ${item.actor}` : ''}
            {showSubject && item.candidate ? (
              <> · <Link className="text-brand-700 hover:underline" to={candidatePath(item.candidate.id, item.application)}>{item.candidate.full_name}</Link></>
            ) : null}
            {showSubject && !item.candidate && item.employee ? (
              <> · <Link className="text-brand-700 hover:underline" to={`/hr/employees/${item.employee.id}`}>{item.employee.full_name}</Link></>
            ) : null}
          </p>
        </li>
      ))}
    </ol>
  )
}

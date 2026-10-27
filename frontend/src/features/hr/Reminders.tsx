import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bell, CalendarClock, Info } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useHrReminders } from '@/hooks/useHr'
import type { Reminder } from '@/types/hr'
import { cn } from '@/utils/cn'
import { formatDateShort } from '@/utils/format'

import { candidatePath, officeDateTime } from './shared'

function when(item: Reminder): string {
  return item.at.length > 10 ? officeDateTime(item.at) : formatDateShort(item.at)
}

function target(item: Reminder): string {
  if (item.candidate) return candidatePath(item.candidate, item.application)
  if (item.vacancy) return `/hr/vacancies/${item.vacancy}`
  return '/hr'
}

/** Список напоминаний (главная HR и выпадающее окно в шапке). Только внутри
 * панели — письма и сообщения не отправляются. */
export function ReminderList({ items, onNavigate, empty = 'Напоминаний нет — всё под контролем.' }: { items: Reminder[]; onNavigate?: () => void; empty?: string }) {
  if (!items.length) return <p className="text-sm text-ink-secondary">{empty}</p>
  return (
    <ul className="divide-y divide-border">
      {items.map((item, index) => {
        const Icon = item.kind === 'interview_soon' ? CalendarClock : item.level === 'warning' ? AlertTriangle : Info
        return (
          <li key={`${item.kind}-${item.interview ?? item.application ?? item.vacancy ?? index}`}>
            <Link to={target(item)} onClick={onNavigate} className="flex gap-3 py-2.5 hover:bg-surface-hover">
              <Icon className={cn('mt-0.5 size-4 shrink-0', item.level === 'warning' ? 'text-warning' : 'text-info')} aria-hidden />
              <span className="min-w-0">
                <span className="block text-sm text-ink">{item.title}</span>
                <span className="block text-xs text-ink-muted">{when(item)}</span>
              </span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

export function RemindersBell() {
  const [open, setOpen] = useState(false)
  const reminders = useHrReminders(false)
  const box = useRef<HTMLDivElement>(null)
  const count = reminders.data?.count ?? 0
  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [open])
  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={count ? `Напоминания — ${count}` : 'Напоминания'}
        className="relative flex size-9 items-center justify-center rounded-full text-ink-muted hover:bg-surface-hover hover:text-ink"
      >
        <Bell className="size-5" aria-hidden />
        {count > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold leading-none text-white">
            {count > 99 ? '99+' : count}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 top-11 z-50 w-[min(22rem,calc(100vw-2rem))] rounded-xl border border-border bg-surface p-3 shadow-lg" role="dialog" aria-label="Напоминания">
          <p className="mb-1 text-sm font-semibold text-ink">Напоминания</p>
          <div className="max-h-96 overflow-y-auto">
            {reminders.isPending ? <p className="text-sm text-ink-secondary">Загрузка…</p>
              : reminders.isError ? <p className="text-sm text-danger">Не удалось загрузить напоминания.</p>
                : <ReminderList items={reminders.data.results} onNavigate={() => setOpen(false)} />}
          </div>
        </div>
      ) : null}
    </div>
  )
}

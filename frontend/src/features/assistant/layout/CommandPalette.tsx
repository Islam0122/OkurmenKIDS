import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  ArrowRightLeft, Award, CalendarDays, CalendarPlus, ClipboardCheck, CornerDownLeft, GraduationCap, Loader2,
  MessageSquarePlus, Search, UserCheck, UserPlus, UserRound, Users, UserX,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { useAssistantSearch } from '@/hooks/useAssistant'
import { useOverlay } from '@/hooks/useOverlay'
import { formatDate } from '@/utils/format'
import { cn } from '@/utils/cn'

import { useAssistantActions } from '../actions/AssistantActions'

interface PaletteItem {
  key: string
  section: string
  label: string
  hint?: string
  icon: LucideIcon
  run: () => void
}

/**
 * «Поиск или Ctrl + K»: one box for students, groups, trainers and the
 * coming week's lessons (GET /assistant/search/), plus the workspace's
 * commands («Создать группу», «Добавить студента», …). Arrows move, Enter
 * opens, Esc closes.
 */
export function CommandPalette({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const { open } = useAssistantActions()
  const [query, setQuery] = useState('')
  const deferred = useDeferredValue(query)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  useOverlay(isOpen, onClose)
  const { data, isFetching } = useAssistantSearch(isOpen ? deferred : '')

  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setActive(0)
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [isOpen])

  const items = useMemo<PaletteItem[]>(() => {
    const go = (to: string) => () => { onClose(); navigate(to) }
    const act = (fn: () => void) => () => { onClose(); fn() }
    const commands: PaletteItem[] = [
      { key: 'c-group', section: 'Команды', label: 'Создать группу', icon: Users, run: act(() => open({ type: 'create-group' })) },
      { key: 'c-student', section: 'Команды', label: 'Добавить студента', icon: UserPlus, run: act(() => open({ type: 'create-student' })) },
      { key: 'c-transfer', section: 'Команды', label: 'Перевести студента', icon: ArrowRightLeft, run: act(() => open({ type: 'transfer' })) },
      { key: 'c-deactivate', section: 'Команды', label: 'Деактивировать студента', icon: UserX, run: act(() => open({ type: 'deactivate' })) },
      { key: 'c-activate', section: 'Команды', label: 'Активировать студента', icon: UserCheck, run: act(() => open({ type: 'activate' })) },
      { key: 'c-schedule', section: 'Команды', label: 'Создать расписание', icon: CalendarPlus, run: act(() => open({ type: 'schedule' })) },
      { key: 'c-open-schedule', section: 'Команды', label: 'Открыть расписание', icon: CalendarDays, run: go('/assistant/schedule') },
      { key: 'c-attendance', section: 'Команды', label: 'Посещаемость сегодня', icon: ClipboardCheck, run: go('/assistant/attendance') },
      { key: 'c-scholarship', section: 'Команды', label: 'Назначить стипендию', icon: Award, run: go('/assistant/scholarships?create=1') },
      { key: 'c-survey', section: 'Команды', label: 'Создать опрос', icon: MessageSquarePlus, run: go('/assistant/surveys?create=1') },
    ]
    const q = query.trim().toLowerCase()
    const matchingCommands = q ? commands.filter((c) => c.label.toLowerCase().includes(q)) : commands
    if (q.length < 2 || !data) return matchingCommands
    return [
      ...data.students.map((s) => ({
        key: `s-${s.id}`, section: 'Студенты', label: s.name, hint: `${s.group ?? 'без группы'} · ${s.status_display}`,
        icon: GraduationCap, run: go(`/assistant/students/${s.id}`),
      })),
      ...data.groups.map((g) => ({
        key: `g-${g.id}`, section: 'Группы', label: g.name, hint: `${g.course} · ${g.status_display}`, icon: Users, run: go(`/assistant/groups/${g.id}`),
      })),
      ...data.teachers.map((t) => ({
        key: `t-${t.id}`, section: 'Тренеры', label: t.name, hint: 'группы тренера', icon: UserRound, run: go(`/assistant/groups?teacher=${t.id}`),
      })),
      ...data.lessons.map((l) => ({
        key: `l-${l.id}`, section: 'Расписание', label: `${l.group.name} — ${formatDate(l.date, false)} ${l.start}`,
        hint: `${l.subject?.name ?? ''} · ${l.teacher?.name ?? ''}`, icon: CalendarDays, run: act(() => open({ type: 'lesson', lesson: l })),
      })),
      ...matchingCommands,
    ]
  }, [data, query, navigate, onClose, open])

  useEffect(() => setActive(0), [items.length])
  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView?.({ block: 'nearest' })
  }, [active])

  if (!isOpen) return null
  let lastSection = ''

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[10vh]">
      <button type="button" aria-label="Закрыть" className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-label="Поиск и команды" className="relative z-10 flex max-h-[70vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl bg-surface shadow-xl">
        <div className="flex items-center gap-2 border-b border-border px-4">
          <Search className="size-4 shrink-0 text-ink-muted" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(i + 1, items.length - 1)) }
              if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)) }
              if (e.key === 'Enter') { e.preventDefault(); items[active]?.run() }
            }}
            placeholder="Студент, группа, тренер или команда…"
            aria-label="Поиск"
            className="h-12 min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted"
          />
          {isFetching ? <Loader2 className="size-4 shrink-0 animate-spin text-ink-muted" aria-hidden /> : null}
        </div>
        <div ref={listRef} className="min-h-0 overflow-y-auto py-1" role="listbox">
          {items.length === 0 ? <p className="px-4 py-6 text-center text-sm text-ink-secondary">Ничего не найдено.</p> : null}
          {items.map((item, index) => {
            const header = item.section !== lastSection ? item.section : null
            lastSection = item.section
            return (
              <div key={item.key}>
                {header ? <p className="px-4 pt-2 pb-1 text-2xs font-semibold tracking-wider text-ink-muted uppercase">{header}</p> : null}
                <button
                  type="button"
                  role="option"
                  aria-selected={index === active}
                  data-index={index}
                  onMouseEnter={() => setActive(index)}
                  onClick={item.run}
                  className={cn('flex w-full items-center gap-3 px-4 py-2 text-left text-sm', index === active ? 'bg-brand-50 text-brand-700' : 'text-ink')}
                >
                  <item.icon className={cn('size-4 shrink-0', index === active ? 'text-brand-600' : 'text-ink-muted')} aria-hidden />
                  <span className="min-w-0 flex-1 truncate font-medium">{item.label}</span>
                  {item.hint ? <span className="hidden max-w-[45%] truncate text-xs text-ink-secondary sm:inline">{item.hint}</span> : null}
                  {index === active ? <CornerDownLeft className="size-3.5 shrink-0" aria-hidden /> : null}
                </button>
              </div>
            )
          })}
        </div>
        <p className="border-t border-border px-4 py-2 text-2xs text-ink-muted">↑↓ — выбрать · Enter — открыть · Esc — закрыть</p>
      </div>
    </div>,
    document.body,
  )
}

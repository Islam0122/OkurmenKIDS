import { useEffect, useRef, useState } from 'react'
import {
  ArrowRightLeft,
  Award,
  CalendarPlus,
  ChevronDown,
  MessageSquarePlus,
  Plus,
  UserCheck,
  UserPlus,
  Users,
  UserX,
  UsersRound,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { cn } from '@/utils/cn'

import { useAssistantActions } from '../actions/AssistantActions'

interface CreateItem {
  key: string
  label: string
  icon: LucideIcon
  run: () => void
  divider?: boolean
}

/** The global «+ Создать» of every Assistant page. */
export function CreateMenu() {
  const [isOpen, setIsOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const { open } = useAssistantActions()

  useEffect(() => {
    if (!isOpen) return
    const onPointer = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setIsOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [isOpen])

  const items: CreateItem[] = [
    { key: 'group', label: 'Группа', icon: Users, run: () => open({ type: 'create-group' }) },
    { key: 'student', label: 'Студент', icon: UserPlus, run: () => open({ type: 'create-student' }) },
    { key: 'schedule', label: 'Расписание', icon: CalendarPlus, run: () => open({ type: 'schedule' }) },
    { key: 'scholarship', label: 'Стипендия', icon: Award, run: () => navigate('/assistant/scholarships?create=1') },
    { key: 'survey', label: 'Опрос', icon: MessageSquarePlus, run: () => navigate('/assistant/surveys?create=1') },
    { key: 'transfer', label: 'Перевести студента', icon: ArrowRightLeft, run: () => open({ type: 'transfer' }), divider: true },
    { key: 'deactivate', label: 'Деактивировать студента', icon: UserX, run: () => open({ type: 'deactivate' }) },
    { key: 'activate', label: 'Активировать студента', icon: UserCheck, run: () => open({ type: 'activate' }) },
    { key: 'to-group', label: 'Добавить студентов в группу', icon: UsersRound, run: () => open({ type: 'bulk', action: 'add_to_group' }) },
  ]

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        className="flex h-9 items-center gap-1.5 rounded-lg bg-brand-500 px-3 text-sm font-medium text-white hover:bg-brand-600"
      >
        <Plus className="size-4" aria-hidden />
        <span className="hidden min-[400px]:inline">Создать</span>
        <ChevronDown className={cn('size-4 transition-transform', isOpen && 'rotate-180')} aria-hidden />
      </button>
      {isOpen ? (
        <div role="menu" className="absolute right-0 z-40 mt-1 w-64 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-lg">
          {items.map((item) => (
            <div key={item.key}>
              {item.divider ? <p className="mt-1 border-t border-border px-3 pt-2 pb-1 text-2xs font-semibold tracking-wider text-ink-muted uppercase">Быстрые действия</p> : null}
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setIsOpen(false)
                  item.run()
                }}
                className="flex min-h-10 w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-ink hover:bg-surface-hover"
              >
                <item.icon className="size-4 shrink-0 text-ink-muted" aria-hidden />
                {item.label}
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

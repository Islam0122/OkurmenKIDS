import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Check, ChevronsUpDown, Search, X } from 'lucide-react'

import type { SelectableStudent } from '@/types/projects'
import { cn } from '@/utils/cn'

import { Avatar } from './shared'

export interface StudentComboboxProps {
  students: SelectableStudent[]
  value: number | null
  onChange: (id: number | null) => void
  invalid?: boolean
  id?: string
  isLoading?: boolean
}

/**
 * Searchable student picker (WAI-ARIA combobox): type a name or a group,
 * ↑/↓ to move, Enter to pick, Esc to close. Results are grouped by group,
 * so a trainer with several groups finds the right child fast.
 */
export function StudentCombobox({ students, value, onChange, invalid, id, isLoading }: StudentComboboxProps) {
  const listId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const selected = students.find((s) => s.id === value) ?? null

  const matches = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean)
    return students.filter((s) => {
      const hay = `${s.full_name} ${s.group?.name ?? ''}`.toLowerCase()
      return words.every((w) => hay.includes(w))
    })
  }, [students, query])

  useEffect(() => setActive(0), [query, open])

  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  useEffect(() => {
    if (!open) return
    document.getElementById(`${listId}-opt-${active}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [active, open, listId])

  const pick = (student: SelectableStudent) => {
    onChange(student.id)
    setQuery('')
    setOpen(false)
  }

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (!open) setOpen(true)
      else setActive((n) => Math.min(n + 1, matches.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((n) => Math.max(n - 1, 0))
    } else if (event.key === 'Enter') {
      if (open && matches[active]) {
        event.preventDefault()
        pick(matches[active])
      }
    } else if (event.key === 'Escape') {
      if (open) {
        event.stopPropagation()
        setOpen(false)
      }
    }
  }

  let lastGroup: string | null = null

  return (
    <div ref={rootRef} className="relative">
      <div
        className={cn(
          'form-control flex h-11 cursor-text items-center gap-2.5 pr-2',
          invalid && 'border-danger',
          open && 'border-brand-500 ring-3 ring-brand-500/10',
        )}
        onClick={() => { setOpen(true); inputRef.current?.focus() }}
      >
        {selected && !open ? (
          <Avatar name={selected.full_name} seed={selected.id} size="xs" />
        ) : (
          <Search className="size-4 shrink-0 text-ink-muted" aria-hidden />
        )}
        <input
          ref={inputRef}
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-invalid={invalid || undefined}
          aria-activedescendant={open && matches[active] ? `${listId}-opt-${active}` : undefined}
          autoComplete="off"
          value={open ? query : selected ? selected.full_name : ''}
          placeholder={selected ? selected.full_name : isLoading ? 'Загружаем студентов…' : 'Начните вводить имя или группу'}
          onChange={(event) => { setQuery(event.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted"
        />
        {selected && !open ? (
          <span className="hidden shrink-0 truncate rounded-md bg-surface-hover px-2 py-0.5 text-xs text-ink-secondary sm:inline">{selected.group?.name}</span>
        ) : null}
        {selected ? (
          <button
            type="button"
            aria-label="Очистить выбор студента"
            onClick={(event) => { event.stopPropagation(); onChange(null); setQuery(''); inputRef.current?.focus() }}
            className="flex size-6 shrink-0 items-center justify-center rounded-md text-ink-muted hover:bg-surface-hover hover:text-ink"
          >
            <X className="size-3.5" aria-hidden />
          </button>
        ) : (
          <ChevronsUpDown className="size-4 shrink-0 text-ink-muted" aria-hidden />
        )}
      </div>

      {open ? (
        <ul
          id={listId}
          role="listbox"
          aria-label="Студенты"
          className="absolute z-30 mt-1.5 max-h-72 w-full overflow-y-auto rounded-xl border border-border bg-surface p-1 shadow-[0_16px_40px_-12px_rgba(32,38,34,0.25)]"
        >
          {matches.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-ink-muted">
              {students.length === 0 ? 'В ваших группах пока нет студентов.' : 'Никого не нашли — проверьте имя.'}
            </li>
          ) : null}
          {matches.map((student, index) => {
            const groupName = student.group?.name ?? 'Без группы'
            const header = groupName !== lastGroup ? groupName : null
            lastGroup = groupName
            const isActive = index === active
            const isSelected = student.id === value
            return [
              header ? (
                <li key={`h-${groupName}`} role="presentation" className="px-3 pb-1 pt-2.5 text-[11px] font-semibold uppercase tracking-wider text-ink-muted first:pt-1.5">
                  {header}
                </li>
              ) : null,
              <li
                key={student.id}
                id={`${listId}-opt-${index}`}
                role="option"
                aria-selected={isSelected}
                onMouseEnter={() => setActive(index)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => pick(student)}
                className={cn(
                  'flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm',
                  isActive ? 'bg-surface-hover' : '',
                )}
              >
                <Avatar name={student.full_name} seed={student.id} size="sm" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-ink">{student.full_name}</span>
                  <span className="block truncate text-xs text-ink-muted">
                    {student.projects_count > 0 ? `Проектов: ${student.projects_count}` : 'Пока без проектов'}
                    {student.status !== 'active' ? ' · не активен' : ''}
                  </span>
                </span>
                {isSelected ? <Check className="size-4 shrink-0 text-brand-600" aria-hidden /> : null}
              </li>,
            ]
          })}
        </ul>
      ) : null}
    </div>
  )
}

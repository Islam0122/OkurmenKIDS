import { useId, useMemo, useRef, useState } from 'react'
import { Plus, X } from 'lucide-react'

import { cn } from '@/utils/cn'

/** Common stacks of the academy's courses — only suggestions; any name can be typed. */
const COMMON_TECHNOLOGIES = [
  'HTML', 'CSS', 'JavaScript', 'TypeScript', 'React', 'Python', 'Scratch', 'Figma', 'Unity', 'C#', 'Node.js', 'Tailwind CSS',
]

export interface TechTagsInputProps {
  value: string[]
  onChange: (value: string[]) => void
  suggestions?: string[]
  max?: number
  id?: string
  invalid?: boolean
}

/** Multi-select tags: Enter or comma adds, Backspace removes the last tag. */
export function TechTagsInput({ value, onChange, suggestions = [], max = 15, id, invalid }: TechTagsInputProps) {
  const [text, setText] = useState('')
  const [focused, setFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const hintId = useId()
  const lower = useMemo(() => new Set(value.map((v) => v.toLowerCase())), [value])

  const pool = useMemo(() => {
    const seen = new Set<string>()
    return [...suggestions, ...COMMON_TECHNOLOGIES].filter((name) => {
      const key = name.toLowerCase()
      if (seen.has(key) || lower.has(key)) return false
      seen.add(key)
      return true
    })
  }, [suggestions, lower])

  const filtered = text ? pool.filter((name) => name.toLowerCase().includes(text.trim().toLowerCase())).slice(0, 8) : pool.slice(0, 10)
  const full = value.length >= max

  const add = (raw: string) => {
    const name = raw.trim().replace(/\s+/g, ' ').slice(0, 50)
    if (!name || lower.has(name.toLowerCase()) || full) return
    onChange([...value, name])
    setText('')
  }

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      add(text)
    } else if (event.key === 'Backspace' && !text && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div>
      <div
        onClick={() => inputRef.current?.focus()}
        className={cn(
          'flex min-h-11 w-full cursor-text flex-wrap items-center gap-1.5 rounded-lg border border-border bg-surface px-2 py-1.5 transition-colors',
          focused && 'border-brand-500 ring-3 ring-brand-500/10',
          invalid && 'border-danger',
        )}
      >
        {value.map((name) => (
          <span key={name} className="inline-flex h-7 items-center gap-1 rounded-md bg-brand-50 pl-2.5 pr-1 text-xs font-medium text-brand-700">
            {name}
            <button
              type="button"
              aria-label={`Убрать ${name}`}
              onClick={(event) => { event.stopPropagation(); onChange(value.filter((v) => v !== name)) }}
              className="flex size-5 items-center justify-center rounded text-brand-700/70 hover:bg-brand-100 hover:text-brand-700"
            >
              <X className="size-3" aria-hidden />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          id={id}
          value={text}
          disabled={full}
          aria-describedby={hintId}
          onChange={(event) => setText(event.target.value.replace(',', ''))}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => { setFocused(false); if (text) add(text) }}
          placeholder={value.length === 0 ? 'React, Python, Figma…' : full ? '' : 'Добавить ещё'}
          className="h-7 min-w-[8rem] flex-1 bg-transparent px-1 text-sm text-ink outline-none placeholder:text-ink-muted"
        />
      </div>
      <p id={hintId} className="mt-1.5 text-xs text-ink-muted">
        {full ? `Не больше ${max} технологий.` : 'Enter или запятая — добавить. Можно выбрать из подсказок.'}
      </p>
      {!full && filtered.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Подсказки технологий">
          {filtered.map((name) => (
            <button
              key={name}
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => add(name)}
              className="inline-flex h-7 items-center gap-1 rounded-md border border-dashed border-border-strong px-2 text-xs text-ink-secondary transition-colors hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
            >
              <Plus className="size-3" aria-hidden />
              {name}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

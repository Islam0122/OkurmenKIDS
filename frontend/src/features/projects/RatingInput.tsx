import { useState } from 'react'
import { Star } from 'lucide-react'

import { cn } from '@/utils/cn'

const LABELS = ['', 'Нужно доработать', 'Неплохо', 'Хорошо', 'Отлично', 'Превосходно']

/** 1–5 stars as a radio group (←/→ change, click the current star again to clear). */
export function RatingInput({ value, onChange }: { value: number | null; onChange: (value: number | null) => void }) {
  const [hover, setHover] = useState<number | null>(null)
  const shown = hover ?? value ?? 0
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
      event.preventDefault()
      onChange(Math.min(5, (value ?? 0) + 1))
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
      event.preventDefault()
      const next = (value ?? 0) - 1
      onChange(next >= 1 ? next : null)
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div role="radiogroup" aria-label="Оценка проекта" className="flex items-center gap-0.5" onMouseLeave={() => setHover(null)} onKeyDown={onKeyDown}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={value === n}
            aria-label={`${n} из 5`}
            tabIndex={(value ?? 1) === n ? 0 : -1}
            onMouseEnter={() => setHover(n)}
            onClick={() => onChange(value === n ? null : n)}
            className="rounded-md p-1 transition-transform hover:scale-110"
          >
            <Star className={cn('size-6 transition-colors', n <= shown ? 'fill-warning text-warning' : 'fill-transparent text-border-strong')} aria-hidden />
          </button>
        ))}
      </div>
      <span className="text-sm text-ink-secondary">{shown ? LABELS[shown] : 'Без оценки'}</span>
      {value ? (
        <button type="button" onClick={() => onChange(null)} className="text-xs font-medium text-ink-muted underline-offset-2 hover:text-ink hover:underline">
          Сбросить
        </button>
      ) : null}
    </div>
  )
}

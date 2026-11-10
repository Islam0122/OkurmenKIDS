import { cn } from '@/utils/cn'

export interface Chip {
  value: string
  label: string
  count?: number
}

/** Horizontally scrollable category filter (touch-friendly on phones). */
export function FilterChips({ chips, value, onChange, label }: { chips: Chip[]; value: string; onChange: (value: string) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="-mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-2 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0">
      {chips.map((chip) => {
        const active = chip.value === value
        return (
          <button
            key={chip.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(chip.value)}
            className={cn(
              'inline-flex h-10 shrink-0 snap-start items-center gap-2 rounded-full border px-4 text-sm font-bold transition',
              active ? 'border-brand-800 bg-brand-800 text-white' : 'border-line bg-white text-ink-soft hover:border-brand-300 hover:text-brand-800',
            )}
          >
            {chip.label}
            {chip.count !== undefined ? (
              <span className={cn('rounded-full px-1.5 text-xs', active ? 'bg-white/20' : 'bg-surface-soft text-muted')}>{chip.count}</span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

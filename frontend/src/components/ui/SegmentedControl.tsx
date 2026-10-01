import { cn } from '@/utils/cn'

export interface SegmentedOption<T extends string> {
  value: T
  label: string
}

export interface SegmentedControlProps<T extends string> {
  options: SegmentedOption<T>[]
  value: T
  onChange: (value: NoInfer<T>) => void
  'aria-label': string
  className?: string
}

/**
 * A single-choice pill switch (period, view mode). On a narrow screen it
 * scrolls horizontally inside itself instead of wrapping into a ragged
 * multi-line block or widening the page.
 */
export function SegmentedControl<T extends string>({ options, value, onChange, className, ...rest }: SegmentedControlProps<T>) {
  return (
    <div className={cn('max-w-full scroll-x', className)}>
      <div role="radiogroup" aria-label={rest['aria-label']} className="inline-flex h-10 items-center gap-1 rounded-lg border border-border bg-surface p-1">
        {options.map((option) => {
          const isActive = option.value === value
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={isActive}
              onClick={() => onChange(option.value)}
              className={cn(
                'h-full shrink-0 whitespace-nowrap rounded-md px-3 text-sm font-medium transition-colors',
                isActive ? 'bg-brand-500 text-white' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink',
              )}
            >
              {option.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

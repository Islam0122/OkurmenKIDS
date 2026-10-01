import { cn } from '@/utils/cn'

export interface TabItem<T extends string> {
  key: T
  label: string
}

export interface TabsProps<T extends string> {
  items: readonly TabItem<T>[]
  value: T
  onChange: (key: NoInfer<T>) => void
  'aria-label': string
}

/** The one underline tab strip (page sections). Scrolls inside itself on a
 * phone rather than wrapping or widening the page. */
export function Tabs<T extends string>({ items, value, onChange, ...rest }: TabsProps<T>) {
  return (
    <div className="mb-6 border-b border-border">
      <div role="tablist" aria-label={rest['aria-label']} className="scroll-x -mb-px flex gap-1">
        {items.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={value === item.key}
            onClick={() => onChange(item.key)}
            className={cn(
              'h-11 shrink-0 whitespace-nowrap border-b-2 px-3 text-sm font-medium transition-colors',
              value === item.key ? 'border-brand-500 text-brand-700' : 'border-transparent text-ink-secondary hover:text-ink',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  )
}

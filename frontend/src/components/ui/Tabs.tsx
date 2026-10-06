import { useEffect, useRef } from 'react'

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
  const strip = useRef<HTMLDivElement>(null)
  // Keep the selected tab visible on a phone (e.g. opened by a link to ?tab=…),
  // scrolling the strip only — never the page.
  useEffect(() => {
    const el = strip.current
    const active = el?.querySelector<HTMLElement>('[aria-selected="true"]')
    if (!el || !active) return
    const left = active.offsetLeft - el.offsetLeft
    if (left < el.scrollLeft || left + active.offsetWidth > el.scrollLeft + el.clientWidth) {
      el.scrollLeft = left - (el.clientWidth - active.offsetWidth) / 2
    }
  }, [value])
  return (
    <div className="mb-6 border-b border-border">
      <div ref={strip} role="tablist" aria-label={rest['aria-label']} className="scroll-x -mb-px flex gap-1">
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

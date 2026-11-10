import type { ReactNode } from 'react'

import { Reveal } from '@/components/shared/Reveal'
import { cn } from '@/utils/cn'

/** Responsive grid with a staggered reveal. On phones `scroll` turns it into a swipeable row. */
export function CardGrid<T>({ items, render, keyOf, columns = 3, scroll }: { items: T[]; render: (item: T) => ReactNode; keyOf: (item: T) => string | number; columns?: 2 | 3 | 4; scroll?: boolean }) {
  const cols = { 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-2 lg:grid-cols-3', 4: 'sm:grid-cols-2 lg:grid-cols-4' }[columns]
  return (
    <ul className={cn(scroll ? '-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-4 [scrollbar-width:none] sm:mx-0 sm:grid sm:gap-6 sm:overflow-visible sm:px-0 sm:pb-0' : 'grid gap-6', cols)}>
      {items.map((item, i) => (
        <Reveal as="li" key={keyOf(item)} delay={Math.min(i, 6) * 0.06} className={cn(scroll && 'w-[82%] shrink-0 snap-start sm:w-auto')}>
          {render(item)}
        </Reveal>
      ))}
    </ul>
  )
}

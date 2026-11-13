import type { ReactNode } from 'react'

import { Reveal } from '@/components/shared/Reveal'
import { cn } from '@/utils/cn'

/** Responsive grid with a staggered reveal. On phones `scroll` turns it into a swipeable row; row counts are balanced. */
export function CardGrid<T>({ items, render, keyOf, columns = 3, scroll }: { items: T[]; render: (item: T, index: number) => ReactNode; keyOf: (item: T) => string | number; columns?: 2 | 3 | 4; scroll?: boolean }) {
  // Balanced rows: never «3 + 1» or «2 + 1».
  //   2 items → 2 columns; 3 items → 3 columns from 768px (a swipe row below);
  //   4 items in a 3-column section → 2×2, then one row of 4 on wide screens.
  const n = items.length
  const three = n === 3 && columns !== 2
  const cols = three
    ? 'md:grid-cols-3'
    : columns === 4
      ? 'sm:grid-cols-2 lg:grid-cols-4'
      : columns === 2 || n === 2
        ? 'sm:grid-cols-2'
        : n === 4
          ? 'sm:grid-cols-2 xl:grid-cols-4'
          : 'sm:grid-cols-2 lg:grid-cols-3'
  // Phones (and, for three items, small tablets): a swipeable row instead of a long stack.
  const swipe = three
    ? '-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-4 [scrollbar-width:none] sm:-mx-6 sm:px-6 md:mx-0 md:grid md:gap-6 md:overflow-visible md:px-0 md:pb-0'
    : '-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-4 [scrollbar-width:none] sm:mx-0 sm:grid sm:gap-6 sm:overflow-visible sm:px-0 sm:pb-0'
  const swipeItem = three ? 'w-[82%] shrink-0 snap-start sm:w-[46%] md:w-auto' : 'w-[82%] shrink-0 snap-start sm:w-auto'
  return (
    <ul className={cn(scroll ? swipe : 'grid gap-6', cols)}>
      {items.map((item, i) => (
        <Reveal as="li" key={keyOf(item)} delay={Math.min(i, 6) * 0.06} className={cn(scroll && swipeItem)}>
          {render(item, i)}
        </Reveal>
      ))}
    </ul>
  )
}

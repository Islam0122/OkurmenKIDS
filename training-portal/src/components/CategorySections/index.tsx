import { useMemo, useState } from 'react'

import type { TrainingTest } from '@/types'

import { t } from '@/i18n'
import { groupByCategory } from '@/lib/categories'
import { storageService } from '@/services/storageService'

import { TestCard } from '../TestCard'
import './CategorySections.css'

/** Trainers split into sections by the category the backend sends (its
 * Subject). With `filter`, chips above let the visitor show one category. */
export function CategorySections({ tests, filter = false }: { tests: TrainingTest[]; filter?: boolean }) {
  const groups = useMemo(() => groupByCategory(tests), [tests])
  const [active, setActive] = useState<string | null>(null)
  const shown = active ? groups.filter((g) => g.key === active) : groups
  const label = (name?: string) => name ?? t.home.otherCategory

  return (
    <div className="categories">
      {filter && groups.length > 1 ? (
        <div className="chips" role="toolbar" aria-label={t.home.categoriesLabel}>
          <button type="button" aria-pressed={!active} className={`chip${!active ? ' is-active' : ''}`} onClick={() => setActive(null)}>
            {t.home.allCategories}
          </button>
          {groups.map((g) => (
            <button key={g.key} type="button" aria-pressed={active === g.key} className={`chip${active === g.key ? ' is-active' : ''}`}
              onClick={() => setActive(g.key)}>
              {label(g.category?.name)}<span className="chip__count">{g.tests.length}</span>
            </button>
          ))}
        </div>
      ) : null}
      {shown.map((g) => (
        <section key={g.key} className="category" aria-labelledby={`category-${g.key}`} data-category={g.category?.slug ?? 'other'}>
          <header className="category__head">
            <h3 className="category__title" id={`category-${g.key}`}>{label(g.category?.name)}</h3>
            <span className="category__count">{t.home.categoryCount(g.tests.length)}</span>
          </header>
          <div className="category__grid">
            {g.tests.map((test) => (
              <TestCard key={test.id} test={test} inProgress={Boolean(storageService.getActiveAttempt(test.id))} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

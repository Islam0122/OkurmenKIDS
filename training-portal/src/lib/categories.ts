import type { TrainerCategory, TrainingTest } from '@/types'

export interface CategoryGroup {
  /** null — trainers without a category (shown last) */
  category: TrainerCategory | null
  key: string
  tests: TrainingTest[]
}

/** Groups trainers by the category the backend sent, keeping the backend's
 * order (categories and trainers are already sorted there). Nothing is
 * hardcoded: the sections are exactly the categories present in the data. */
export function groupByCategory(tests: TrainingTest[]): CategoryGroup[] {
  const groups = new Map<string, CategoryGroup>()
  for (const test of tests) {
    const key = test.category ? `c${test.category.id}` : 'none'
    const group = groups.get(key) ?? { category: test.category, key, tests: [] }
    group.tests.push(test)
    groups.set(key, group)
  }
  const ordered = [...groups.values()]
  return [...ordered.filter((g) => g.category), ...ordered.filter((g) => !g.category)]
}

import type { Paginated } from '@/types/common'

/**
 * Walks every page of a paginated endpoint and flattens the results.
 *
 * Only for the handful of call sites aggregating a single day's/teacher's
 * inherently small dataset for a dashboard-style stat (e.g. "today's
 * attendance") — real list *pages* (Students, Lessons, Homework…) must keep
 * using the backend's own pagination and never load everything at once.
 */
export async function fetchAllPages<T>(fetchPage: (page: number) => Promise<Paginated<T>>): Promise<T[]> {
  const first = await fetchPage(1)
  const pageSize = first.results.length || 20
  const totalPages = pageSize > 0 ? Math.ceil(first.count / pageSize) : 1

  if (totalPages <= 1) {
    return first.results
  }

  const rest = await Promise.all(
    Array.from({ length: totalPages - 1 }, (_, index) => fetchPage(index + 2)),
  )

  return [...first.results, ...rest.flatMap((page) => page.results)]
}

import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * Filters and page in the URL (?category=python&page=2) — shareable,
 * indexable, and the back button works.
 */
export function useListParams(keys: string[] = ['category', 'q']) {
  const [search, setSearch] = useSearchParams()
  const params = useMemo(() => {
    const out: Record<string, string> = {}
    for (const key of keys) out[key] = search.get(key) ?? ''
    return out
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, keys.join(",")])
  const page = Math.max(1, Number(search.get('page')) || 1)

  const update = useCallback(
    (next: Record<string, string | number | undefined>) => {
      setSearch((prev) => {
        const copy = new URLSearchParams(prev)
        for (const [key, value] of Object.entries(next)) {
          if (value === undefined || value === '' || value === 'all' || (key === 'page' && value === 1)) copy.delete(key)
          else copy.set(key, String(value))
        }
        if (!('page' in next)) copy.delete('page')
        return copy
      }, { replace: false })
      if ('page' in next) window.scrollTo({ top: 0, behavior: 'smooth' })
    },
    [setSearch],
  )
  return { params, page, update }
}

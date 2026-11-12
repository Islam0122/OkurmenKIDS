import { useCallback } from 'react'

import { toList, useSiteList, type Choice, type SiteMeta } from './api'

/** Choices of select fields: meta.choices, LMS courses / trainers, site branches. */
export function useChoices(meta: SiteMeta | undefined) {
  const branches = useSiteList('branches', {})
  return useCallback((source?: string): Choice[] => {
    if (!source) return []
    if (source === 'lms:courses') return (meta?.lms?.courses ?? []).map((c) => ({ value: String(c.id), label: `${c.name} (${c.lessons} зан.)` }))
    if (source === 'lms:teachers') return (meta?.lms?.teachers ?? []).map((t) => ({ value: String(t.id), label: `${t.name} — ${t.position}` }))
    if (source === 'branches') return toList(branches.data).rows.map((b) => ({ value: String(b.id), label: String(b.name) }))
    return meta?.choices[source] ?? []
  }, [meta, branches.data])
}

import { Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { useI18n } from '@/i18n'

/** Debounced search input. */
export function SearchBox({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useI18n()
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  useEffect(() => {
    const id = window.setTimeout(() => {
      if (draft !== value) onChange(draft.trim())
    }, 350)
    return () => window.clearTimeout(id)
  }, [draft, value, onChange])
  return (
    <label className="relative block w-full sm:max-w-xs">
      <span className="sr-only">{t('filter.search')}</span>
      <Search className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-muted" aria-hidden />
      <input type="search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={t('filter.searchPlaceholder')} className="input h-11 rounded-full pr-10 pl-10" />
      {draft ? (
        <button type="button" onClick={() => setDraft('')} className="absolute top-1/2 right-3 grid size-7 -translate-y-1/2 place-items-center rounded-full text-muted hover:bg-brand-50" aria-label="×">
          <X className="size-4" aria-hidden />
        </button>
      ) : null}
    </label>
  )
}

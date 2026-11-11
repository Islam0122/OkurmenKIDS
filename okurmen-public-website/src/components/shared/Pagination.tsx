import { ChevronLeft, ChevronRight } from 'lucide-react'

import { useI18n } from '@/i18n'
import { cn } from '@/utils/cn'

export function Pagination({ page, total, onChange }: { page: number; total: number; onChange: (page: number) => void }) {
  const { t } = useI18n()
  if (total <= 1) return null
  const pages = Array.from({ length: total }, (_, i) => i + 1).filter((p) => p === 1 || p === total || Math.abs(p - page) <= 1)
  const button = 'grid size-11 place-items-center rounded-full text-sm font-bold transition disabled:opacity-40'
  return (
    <nav className="mt-12 flex items-center justify-center gap-1.5" aria-label={t('pagination.page', { page, total })}>
      <button type="button" className={cn(button, 'hover:bg-brand-50')} disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label={t('pagination.prev')}>
        <ChevronLeft className="size-5" aria-hidden />
      </button>
      {pages.map((p, index) => (
        <span key={p} className="flex items-center gap-1.5">
          {index > 0 && p - pages[index - 1] > 1 ? <span className="px-1 text-muted">…</span> : null}
          <button
            type="button"
            onClick={() => onChange(p)}
            aria-current={p === page ? 'page' : undefined}
            className={cn(button, p === page ? 'bg-brand-800 text-white' : 'hover:bg-brand-50')}
          >
            {p}
          </button>
        </span>
      ))}
      <button type="button" className={cn(button, 'hover:bg-brand-50')} disabled={page >= total} onClick={() => onChange(page + 1)} aria-label={t('pagination.next')}>
        <ChevronRight className="size-5" aria-hidden />
      </button>
    </nav>
  )
}

import { useState } from 'react'
import { ExternalLink, FolderKanban, Home, Star } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { SearchInput } from '@/components/ui/SearchInput'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { siteCmsApi, useSiteInvalidate, type CmsProject } from './api'
import { CmsPage, formatDate, Skeleton } from './ui'

/**
 * /marketing/site/projects — проекты учеников на сайте. Проекты регистрируют
 * тренеры в LMS (apps.projects: создаёт только тренер), здесь маркетинг
 * видит опубликованные и выбирает, какие показать на главной.
 */
export function ProjectsPage() {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const [search, setSearch] = useState('')
  const [only, setOnly] = useState(false)
  const [busy, setBusy] = useState<number | null>(null)
  const query = useQuery({ queryKey: ['site-cms', 'projects', search], queryFn: () => siteCmsApi.projects(search) })
  const rows = (query.data?.results ?? []).filter((p) => !only || p.is_featured)
  const featured = (query.data?.results ?? []).filter((p) => p.is_featured).length

  const toggle = async (p: CmsProject) => {
    setBusy(p.id)
    try {
      await siteCmsApi.featureProject(p.id, !p.is_featured)
      await invalidate()
      showToast(p.is_featured ? 'Проект убран с главной' : 'Проект добавлен на главную', 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    } finally {
      setBusy(null)
    }
  }

  return (
    <CmsPage title="Проекты учеников" description="Опубликованные тренерами работы студентов — так, как их видит сайт. Отметьте ★, чтобы показать проект на главной; ничего не отмечено — сайт берёт последние.">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="sm:w-72"><SearchInput value={search} onChange={setSearch} placeholder="Название или студент" /></div>
        <div role="group" aria-label="Фильтр" className="inline-flex rounded-xl border border-border bg-surface p-1 text-sm">
          <button type="button" aria-pressed={!only} onClick={() => setOnly(false)} className={cn('h-8 rounded-lg px-3 font-medium', !only ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary')}>Все</button>
          <button type="button" aria-pressed={only} onClick={() => setOnly(true)} className={cn('h-8 rounded-lg px-3 font-medium', only ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary')}>На главной ({featured})</button>
        </div>
      </div>
      <p className="rounded-xl bg-info-soft px-4 py-2.5 text-sm text-info">Новый проект добавляет тренер группы в LMS («Проекты студентов») — так сохраняется связь с учеником и согласие на публикацию.</p>

      {query.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-64 rounded-2xl" />)}</div>
      ) : query.isError ? <ErrorState message={extractErrorMessage(query.error)} onRetry={() => query.refetch()} /> : rows.length ? (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {rows.map((p) => (
            <li key={p.id} className={cn('flex flex-col overflow-hidden rounded-2xl border bg-surface', p.is_featured ? 'border-cms-gold ring-1 ring-cms-gold/40' : 'border-border')}>
              <div className="relative aspect-[4/3] bg-surface-muted">
                {p.cover ? <img src={p.cover} alt="" className="size-full object-cover" loading="lazy" /> : <FolderKanban className="absolute inset-0 m-auto size-8 text-ink-muted" aria-hidden />}
                {p.is_featured ? <span className="absolute top-2 left-2 inline-flex items-center gap-1 rounded-full bg-cms-gold px-2 py-0.5 text-xs font-semibold text-brand-700"><Home className="size-3" aria-hidden />На главной</span> : null}
              </div>
              <div className="flex flex-1 flex-col p-3">
                <p className="line-clamp-2 font-medium text-ink">{p.title}</p>
                <p className="mt-0.5 text-xs text-ink-muted">{[p.student, p.group, formatDate(p.date)].filter(Boolean).join(' · ')}</p>
                {p.technologies.length ? <p className="mt-2 flex flex-wrap gap-1">{p.technologies.slice(0, 4).map((t) => <span key={t} className="rounded-md bg-surface-hover px-1.5 py-0.5 text-[0.6875rem] text-ink-secondary">{t}</span>)}</p> : null}
                <div className="mt-auto flex items-center gap-2 pt-3">
                  <button type="button" onClick={() => toggle(p)} disabled={busy === p.id} aria-pressed={p.is_featured}
                    className={cn('inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-lg text-sm font-medium disabled:opacity-50',
                      p.is_featured ? 'bg-cms-gold-soft text-cms-gold-deep hover:bg-cms-gold/30' : 'border border-brand-200 text-brand-700 hover:bg-brand-50')}>
                    <Star className={cn('size-4', p.is_featured && 'fill-current')} aria-hidden />{p.is_featured ? 'Убрать с главной' : 'На главную'}
                  </button>
                  {p.public_url ? <a href={p.public_url} target="_blank" rel="noreferrer" aria-label={`Открыть «${p.title}» на сайте`} className="grid size-9 place-items-center rounded-lg text-ink-secondary hover:bg-surface-hover"><ExternalLink className="size-4" aria-hidden /></a> : null}
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState icon={FolderKanban} title={only ? 'На главной пока нет проектов' : search ? 'Ничего не найдено' : 'Опубликованных проектов пока нет'}
          description={only ? 'Отметьте проекты звёздочкой во вкладке «Все».' : 'Когда тренеры опубликуют работы студентов в LMS, они появятся здесь.'} />
      )}
    </CmsPage>
  )
}

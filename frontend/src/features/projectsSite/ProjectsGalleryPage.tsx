import { useEffect, useState } from 'react'
import { keepPreviousData, useInfiniteQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { AlertTriangle, FolderKanban, Loader2, Search, SearchX, X } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { PROJECT_CATEGORIES, publicProjectsApi, type ProjectCategory } from '@/api/publicProjects'
import { useI18n } from '@/features/portal/i18n'
import { PortalShell } from '@/features/portal/PortalShell'
import { cn } from '@/utils/cn'

import { ProjectCard, ProjectCardSkeleton } from './ProjectCard'
import { StatusBlock, buttonPrimary, buttonSecondary } from './StatusBlock'

const PAGE_SIZE = 12
const SEARCH_DELAY_MS = 300

function isCategory(value: string | null): value is ProjectCategory {
  return (PROJECT_CATEGORIES as readonly string[]).includes(value ?? '')
}

/** /projects — the public gallery of published student projects (no login). */
export function ProjectsGalleryPage() {
  return (
    <PortalShell title={(t) => t.gallery.title} backHome>
      <Gallery />
    </PortalShell>
  )
}

function Gallery() {
  const { t } = useI18n()
  const g = t.gallery
  const [params, setParams] = useSearchParams()
  const category: ProjectCategory = isCategory(params.get('category')) ? (params.get('category') as ProjectCategory) : 'all'
  const q = (params.get('q') ?? '').trim()
  const [draft, setDraft] = useState(q)

  // The search box writes to the URL after a short pause, so a link keeps the search.
  useEffect(() => {
    const value = draft.trim()
    if (value === q) return
    const id = window.setTimeout(() => {
      setParams((prev) => {
        const next = new URLSearchParams(prev)
        if (value) next.set('q', value)
        else next.delete('q')
        return next
      }, { replace: true })
    }, SEARCH_DELAY_MS)
    return () => window.clearTimeout(id)
  }, [draft, q, setParams])

  function choose(next: ProjectCategory) {
    setParams((prev) => {
      const out = new URLSearchParams(prev)
      if (next === 'all') out.delete('category')
      else out.set('category', next)
      return out
    }, { replace: true })
  }

  function reset() {
    setDraft('')
    setParams(new URLSearchParams(), { replace: true })
  }

  const query = useInfiniteQuery({
    queryKey: ['public-projects', { q, category }],
    queryFn: ({ pageParam }) => publicProjectsApi.list({ q, category, page: pageParam, page_size: PAGE_SIZE }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page < last.num_pages ? last.page + 1 : undefined),
    placeholderData: keepPreviousData,
  })

  const first = query.data?.pages[0]
  const projects = query.data?.pages.flatMap((page) => page.results) ?? []
  const counts = first?.counts
  const filtered = Boolean(q) || category !== 'all'

  return (
    <main className="mx-auto w-full max-w-[1100px] flex-1 px-4 pb-12 pt-4 sm:px-6 sm:pt-8">
      <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="text-center">
        <span className="mx-auto grid size-12 place-items-center rounded-2xl border border-pd-green-line bg-pd-green-soft text-pd-green pd-shadow">
          <FolderKanban className="size-6" strokeWidth={1.75} aria-hidden />
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-[-0.03em] sm:text-4xl lg:text-[2.6rem]">{g.title}</h1>
        <p className="mx-auto mt-2.5 max-w-xl text-pretty text-sm text-pd-muted sm:text-base">{g.description}</p>
      </motion.section>

      <div className="sticky top-0 z-20 -mx-4 mt-7 border-b border-transparent bg-pd-bg/85 px-4 py-3 backdrop-blur-md sm:-mx-6 sm:px-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <label className="relative block w-full lg:max-w-[17rem] lg:shrink-0">
            <span className="sr-only">{g.searchLabel}</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-pd-faint" aria-hidden />
            <input
              type="search"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={g.search}
              maxLength={100}
              className="h-11 w-full rounded-xl border border-pd-line bg-pd-panel pl-9 pr-9 text-sm text-pd-ink pd-shadow outline-none transition placeholder:text-pd-faint focus:border-pd-green focus:ring-4 focus:ring-pd-green/15 [&::-webkit-search-cancel-button]:hidden"
            />
            {draft ? (
              <button
                type="button"
                onClick={() => setDraft('')}
                aria-label={g.clearSearch}
                className="absolute right-2 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded-full text-pd-faint transition hover:bg-zinc-100 hover:text-pd-ink"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            ) : null}
          </label>

          <div role="group" aria-label={g.filtersLabel} className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0 sm:pb-0 lg:justify-end [&::-webkit-scrollbar]:hidden">
            {PROJECT_CATEGORIES.map((id) => {
              const active = id === category
              const count = counts?.[id]
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => choose(id)}
                  aria-pressed={active}
                  className={cn(
                    'inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pd-green',
                    active
                      ? 'border-pd-green bg-pd-green text-white pd-shadow'
                      : 'border-pd-line bg-pd-panel text-pd-muted hover:border-pd-green-line hover:text-pd-ink',
                  )}
                >
                  {g.filters[id]}
                  {count !== undefined ? (
                    <span className={cn('rounded-full px-1.5 text-[11px] font-semibold tabular-nums', active ? 'bg-white/20 text-white' : 'bg-zinc-100 text-pd-faint')}>
                      {count}
                    </span>
                  ) : null}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      <div className="mt-5" aria-live="polite" aria-busy={query.isFetching}>
        {query.isPending ? (
          <>
            <p className="sr-only">{g.loading}</p>
            <ul className="grid gap-4 sm:grid-cols-2 sm:gap-5 lg:grid-cols-3">
              {Array.from({ length: 6 }, (_, index) => (
                <ProjectCardSkeleton key={index} />
              ))}
            </ul>
          </>
        ) : query.isError && !query.data ? (
          <StatusBlock
            icon={AlertTriangle}
            tone="danger"
            title={g.errorTitle}
            text={g.errorText}
            action={
              <button type="button" className={buttonPrimary} onClick={() => void query.refetch()}>
                {g.retry}
              </button>
            }
          />
        ) : projects.length === 0 ? (
          filtered ? (
            <StatusBlock
              icon={SearchX}
              title={g.noResultsTitle}
              text={g.noResultsText}
              action={
                <button type="button" className={buttonSecondary} onClick={reset}>
                  {g.reset}
                </button>
              }
            />
          ) : (
            <StatusBlock icon={FolderKanban} title={g.emptyTitle} text={g.emptyText} />
          )
        ) : (
          <>
            <p className="mb-3 text-sm text-pd-faint">{g.found(first?.count ?? projects.length)}</p>
            <motion.ul
              key={`${q}|${category}`}
              initial="hidden"
              animate="show"
              variants={{ hidden: {}, show: { transition: { staggerChildren: 0.04 } } }}
              className={cn('grid gap-4 transition-opacity sm:grid-cols-2 sm:gap-5 lg:grid-cols-3', query.isPlaceholderData && 'opacity-60')}
            >
              {projects.map((project) => (
                <ProjectCard key={project.key} project={project} />
              ))}
            </motion.ul>
            {query.hasNextPage ? (
              <div className="mt-8 flex justify-center">
                <button type="button" className={buttonSecondary} onClick={() => void query.fetchNextPage()} disabled={query.isFetchingNextPage}>
                  {query.isFetchingNextPage ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
                  {g.loadMore}
                </button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </main>
  )
}

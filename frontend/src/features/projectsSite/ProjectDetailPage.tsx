import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { motion } from 'framer-motion'
import { AlertTriangle, ArrowLeft, CalendarDays, ExternalLink, FolderKanban, GraduationCap, ImageOff, SearchX, UserRound, UsersRound } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { publicProjectsApi, type PublicProject } from '@/api/publicProjects'
import { useI18n } from '@/features/portal/i18n'
import { Lightbox } from '@/features/portal/Lightbox'
import { PortalShell } from '@/features/portal/PortalShell'
import { resolveMediaUrl } from '@/lib/mediaUrl'
import { cn } from '@/utils/cn'

import { formatProjectDate } from './format'
import { StatusBlock, buttonPrimary, buttonSecondary } from './StatusBlock'

const backLink =
  'inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-pd-muted transition hover:text-pd-green focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-pd-green'

/** /projects/:key — one published project (no login). */
export function ProjectDetailPage() {
  const { key = '' } = useParams()
  const query = useQuery({
    queryKey: ['public-project', key],
    queryFn: () => publicProjectsApi.detail(key),
    retry: (count, error) => !(isAxiosError(error) && error.response?.status === 404) && count < 1,
  })
  return (
    <PortalShell title={(t) => query.data?.title ?? t.gallery.title} backHome>
      <Detail query={query} />
    </PortalShell>
  )
}

function Detail({ query }: { query: ReturnType<typeof useQuery<PublicProject>> }) {
  const { t } = useI18n()
  const g = t.gallery
  const notFound = isAxiosError(query.error) && query.error.response?.status === 404

  return (
    <main className="mx-auto w-full max-w-[1100px] flex-1 px-4 pb-12 pt-4 sm:px-6 sm:pt-6">
      <Link to="/projects" className={backLink}>
        <ArrowLeft className="size-4" aria-hidden /> {g.back}
      </Link>

      <div className="mt-5" aria-live="polite" aria-busy={query.isFetching}>
        {query.isPending ? (
          <DetailSkeleton label={g.loading} />
        ) : notFound ? (
          <StatusBlock
            icon={SearchX}
            title={g.notFoundTitle}
            text={g.notFoundText}
            action={
              <Link to="/projects" className={buttonSecondary}>
                {g.back}
              </Link>
            }
          />
        ) : query.isError ? (
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
        ) : (
          <ProjectView project={query.data} />
        )}
      </div>
    </main>
  )
}

function ProjectView({ project }: { project: PublicProject }) {
  const { t, lang } = useI18n()
  const g = t.gallery
  const images = project.images.map((image) => resolveMediaUrl(image.url)).filter((url): url is string => Boolean(url))
  const [active, setActive] = useState(0)
  const [viewer, setViewer] = useState<number | null>(null)

  const meta = [
    { icon: UserRound, label: g.student, value: project.student ?? g.hiddenStudent },
    project.group ? { icon: UsersRound, label: g.group, value: project.group } : null,
    project.trainer ? { icon: GraduationCap, label: g.trainer, value: project.trainer } : null,
    { icon: CalendarDays, label: g.date, value: formatProjectDate(project.date, lang) },
  ].filter((row): row is NonNullable<typeof row> => row !== null)

  return (
    <motion.article initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)] lg:gap-8">
        <section aria-label={g.gallery} className="min-w-0">
          {images.length > 0 ? (
            <>
              <button
                type="button"
                onClick={() => setViewer(active)}
                className="group relative block aspect-[16/10] w-full overflow-hidden rounded-2xl border border-pd-line bg-pd-subtle pd-shadow outline-none focus-visible:ring-4 focus-visible:ring-pd-green/20"
                aria-label={g.open(active + 1)}
              >
                <img src={images[active]} alt={g.screenshot(active + 1, images.length)} className="size-full object-contain transition-transform duration-500 group-hover:scale-[1.02]" />
              </button>
              {images.length > 1 ? (
                <ul className="mt-3 grid grid-cols-4 gap-2 sm:grid-cols-6">
                  {images.map((url, index) => (
                    <li key={url}>
                      <button
                        type="button"
                        onClick={() => setActive(index)}
                        onDoubleClick={() => setViewer(index)}
                        aria-label={g.screenshot(index + 1, images.length)}
                        aria-current={index === active}
                        className={cn(
                          'block aspect-[4/3] w-full overflow-hidden rounded-lg border bg-pd-subtle outline-none transition focus-visible:ring-4 focus-visible:ring-pd-green/20',
                          index === active ? 'border-pd-green ring-2 ring-pd-green/30' : 'border-pd-line opacity-80 hover:opacity-100',
                        )}
                      >
                        <img src={url} alt="" loading="lazy" className="size-full object-cover" />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <div className="flex aspect-[16/10] w-full flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-pd-line-strong bg-gradient-to-br from-pd-green-soft to-white text-pd-muted">
              <ImageOff className="size-7 text-pd-green" strokeWidth={1.75} aria-hidden />
              <span className="text-sm">{g.noImages}</span>
            </div>
          )}
        </section>

        <section className="min-w-0">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-pd-green-line bg-pd-green-soft px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-pd-green-deep">
            <FolderKanban className="size-3.5" aria-hidden />
            {g.title}
          </span>
          <h1 className="mt-3 text-balance text-2xl font-extrabold tracking-[-0.02em] sm:text-3xl">{project.title}</h1>
          {project.short_description ? <p className="mt-2 text-pd-muted">{project.short_description}</p> : null}

          <dl className="mt-5 grid gap-px overflow-hidden rounded-xl border border-pd-line bg-pd-line">
            {meta.map(({ icon: Icon, label, value }) => (
              <div key={label} className="flex items-center justify-between gap-4 bg-pd-panel px-4 py-3 text-sm">
                <dt className="inline-flex items-center gap-2 text-pd-faint">
                  <Icon className="size-4 text-pd-green" aria-hidden />
                  {label}
                </dt>
                <dd className="min-w-0 truncate text-right font-medium">{value}</dd>
              </div>
            ))}
          </dl>

          {project.technologies.length > 0 ? (
            <div className="mt-5">
              <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-pd-faint">{g.technologies}</h2>
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {project.technologies.map((tech) => (
                  <li key={tech} className="rounded-full border border-pd-green-line bg-pd-green-soft px-2.5 py-0.5 text-xs font-medium text-pd-green-deep">
                    {tech}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {project.demo_url ? (
            <a href={project.demo_url} target="_blank" rel="noopener noreferrer nofollow" className={cn(buttonPrimary, 'mt-6 w-full sm:w-auto')}>
              <ExternalLink className="size-4" aria-hidden />
              {g.demo}
            </a>
          ) : null}
        </section>
      </div>

      {project.description ? (
        <section className="mt-8 rounded-2xl border border-pd-line bg-pd-panel p-5 pd-shadow sm:p-6">
          <h2 className="text-lg font-bold tracking-tight">{g.about}</h2>
          <p className="mt-3 whitespace-pre-line text-[15px] leading-relaxed text-pd-muted [overflow-wrap:anywhere]">{project.description}</p>
        </section>
      ) : null}

      <Lightbox images={images.map((src) => ({ src }))} index={viewer} onIndex={setViewer} label={g.screenshot} prev={g.prev} next={g.next} />
    </motion.article>
  )
}

function DetailSkeleton({ label }: { label: string }) {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)] lg:gap-8" aria-hidden={false}>
      <p className="sr-only">{label}</p>
      <div className="aspect-[16/10] animate-pulse rounded-2xl bg-zinc-100" />
      <div className="space-y-3">
        <div className="h-5 w-32 animate-pulse rounded-full bg-zinc-100" />
        <div className="h-8 w-3/4 animate-pulse rounded bg-zinc-100" />
        <div className="h-4 w-full animate-pulse rounded bg-zinc-100" />
        <div className="h-40 animate-pulse rounded-xl bg-zinc-100" />
      </div>
    </div>
  )
}

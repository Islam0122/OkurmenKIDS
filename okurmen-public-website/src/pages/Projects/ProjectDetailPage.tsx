import { CalendarDays, Code2, ExternalLink, GraduationCap, Layers, UserRound, Users } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { ProjectCard } from '@/components/cards/ProjectCard'
import { ButtonLink } from '@/components/shared/Button'
import { PageHero } from '@/components/shared/PageHero'
import { Reveal } from '@/components/shared/Reveal'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { crumbsLd, detailDescription, detailTitle, Seo } from '@/components/shared/Seo'
import { SmartImage } from '@/components/shared/SmartImage'
import { ErrorState, NotFoundState, PageSkeleton } from '@/components/shared/States'
import { Gallery } from '@/features/content/Gallery'
import { RichText } from '@/features/content/RichText'
import { ShareButton } from '@/features/content/ShareButton'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { isNotFound, useProject, useProjects } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { ProjectDetail } from '@/types/api'
import { absoluteUrl, mediaUrl } from '@/utils/media'
import { BRAND } from '@/app/config/site'
import { projectText, type Lang } from '@/seo/core'

/** Student projects are published in Russian only (apps.projects has no translations). */
const PROJECT_LANGS: Lang[] = ['ru']

const WIDE = 'mx-auto w-[calc(100%-48px)] max-w-[1280px]'

function hostOf(url: string | null): string | null {
  if (!url) return null
  try {
    return new URL(url).host.replace(/^www\./, '')
  } catch {
    return null
  }
}

export function ProjectDetailPage() {
  const { slug = '' } = useParams()
  const { data: project, isPending, isError, error, refetch } = useProject(slug)
  if (isPending) return <PageSkeleton />
  if (isError) return isNotFound(error) ? <NotFoundState /> : <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>
  return <ProjectView project={project} />
}

function ProjectView({ project }: { project: ProjectDetail }) {
  const { t, path, formatDate, lang } = useI18n()
  const author = project.student ?? t('projects.anonymous')
  const host = hostOf(project.demo_url)
  // Screenshots = every image except the cover shown at the top.
  const screenshots = project.images
    .filter((img) => img.url !== project.cover_url)
    .map((img) => ({ url: img.url, thumb: img.url, width: null, height: null, caption: '' }))

  const facts = [
    { icon: UserRound, label: t('projects.student'), value: author },
    project.group ? { icon: Users, label: t('projects.group'), value: project.group } : null,
    project.trainer ? { icon: GraduationCap, label: t('projects.trainer'), value: project.trainer } : null,
    { icon: CalendarDays, label: t('projects.date'), value: formatDate(project.date) },
    project.categories.length ? { icon: Layers, label: t('projects.filter.category'), value: project.categories.map((c) => t(`projects.cat.${c}`)).join(', ') } : null,
  ].filter(Boolean) as { icon: typeof UserRound; label: string; value: string }[]

  return (
    <>
      <Seo
        title={detailTitle(lang, 'projects', project.title, null, project.short_description)}
        description={detailDescription(lang, 'projects', projectText(project, lang))}
        image={project.cover_url}
        type="article"
        langs={PROJECT_LANGS}
        jsonLd={[
          crumbsLd(lang, 'projects', { name: project.title, slug: project.key }),
          {
            '@context': 'https://schema.org',
            '@type': 'CreativeWork',
            name: project.title,
            description: project.short_description,
            dateCreated: project.date,
            // Student projects are published in Russian only: the canonical is the Russian URL.
            url: absoluteUrl(`/projects/${project.key}`),
            keywords: project.technologies.join(', '),
            ...(project.cover_url ? { image: absoluteUrl(mediaUrl(project.cover_url) ?? '') } : {}),
            ...(project.student ? { creator: { '@type': 'Person', name: project.student } } : {}),
            publisher: { '@type': 'EducationalOrganization', '@id': absoluteUrl('/#organization'), name: BRAND.name, url: absoluteUrl('/') },
          },
        ]}
      />
      <PageHero compact wide title={project.title} text={project.short_description} crumbs={[{ label: t('nav.projects'), to: '/projects' }, { label: project.title }]}>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          {project.demo_url ? (
            <ButtonLink to={project.demo_url} size="lg">{t('projects.demo')} <ExternalLink className="size-5" aria-hidden /></ButtonLink>
          ) : null}
          <ShareButton title={project.title} />
        </div>
      </PageHero>

      <div className={`${WIDE} grid gap-8 py-8 sm:py-10 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-10 lg:py-12 xl:grid-cols-[minmax(0,1fr)_24rem]`}>
        <div className="min-w-0 space-y-10">
          {/* Large preview in a browser frame */}
          <Reveal>
            <figure className="overflow-hidden rounded-[1.75rem] border border-line bg-white shadow-lift">
              <div className="flex items-center gap-2 border-b border-line bg-surface-soft px-4 py-3">
                <span className="size-3 rounded-full bg-rose-300" aria-hidden /><span className="size-3 rounded-full bg-gold-300" aria-hidden /><span className="size-3 rounded-full bg-emerald-300" aria-hidden />
                <span className="ml-3 min-w-0 flex-1 truncate rounded-md bg-white px-3 py-1 text-xs text-muted">{host ?? project.title}</span>
              </div>
              <div className="relative aspect-video bg-gradient-to-br from-brand-50 to-surface-soft">
                <SmartImage src={project.cover_url} alt={project.title} priority sizes="(min-width: 1024px) 66vw, 100vw" className="size-full object-cover object-top"
                  fallback={<Code2 className="size-16 text-brand-300" aria-hidden />} />
              </div>
            </figure>
          </Reveal>

          {project.description ? (
            <section>
              <h2 className="mb-4 text-2xl font-black sm:text-3xl">{t('projects.about')}</h2>
              <RichText source={project.description} />
            </section>
          ) : null}

          {screenshots.length ? (
            <section>
              <h2 className="mb-5 text-2xl font-black sm:text-3xl">{t('projects.gallery')}</h2>
              <Gallery photos={screenshots} title={project.title} />
            </section>
          ) : null}
        </div>

        <aside className="space-y-5 lg:sticky lg:top-24 lg:self-start">
          <div className="card overflow-hidden">
            <dl className="divide-y divide-line">
              {facts.map((row) => (
                <div key={row.label} className="flex items-center gap-3 px-5 py-4">
                  <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><row.icon className="size-4" aria-hidden /></span>
                  <div className="min-w-0">
                    <dt className="text-xs font-bold tracking-wide text-muted uppercase">{row.label}</dt>
                    <dd className="font-bold break-words text-ink">{row.value}</dd>
                  </div>
                </div>
              ))}
            </dl>
            {project.technologies.length ? (
              <div className="border-t border-line px-5 py-4">
                <p className="mb-2.5 text-xs font-bold tracking-wide text-muted uppercase">{t('projects.technologies')}</p>
                <ul className="flex flex-wrap gap-1.5">
                  {project.technologies.map((tech) => (
                    <li key={tech}>
                      <Link to={path(`/projects?technology=${encodeURIComponent(tech)}`)} className="inline-flex min-h-10 items-center rounded-lg bg-surface-purple px-3 text-sm font-bold text-brand-700 transition hover:bg-brand-100">{tech}</Link>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {project.demo_url ? (
              <div className="border-t border-line p-5">
                <ButtonLink to={project.demo_url} className="w-full">{t('projects.demo')} <ExternalLink className="size-4" aria-hidden /></ButtonLink>
                {host ? <p className="mt-2 truncate text-center text-xs text-muted">{host}</p> : null}
              </div>
            ) : null}
          </div>
          <p className="px-1 text-xs text-muted">{t('projects.authorNote')}</p>
          <div className="rounded-3xl bg-brand-800 p-6 text-white">
            <p className="font-display text-xl font-black text-white">{t('projects.cta.title')}</p>
            <p className="mt-2 text-sm text-white/80">{t('projects.cta.text')}</p>
            <EnrollButton className="mt-5 w-full" />
          </div>
        </aside>
      </div>

      <RelatedProjects project={project} />
    </>
  )
}

/** Other published projects of the same direction (the same public API). */
function RelatedProjects({ project }: { project: ProjectDetail }) {
  const { t } = useI18n()
  const category: string = project.categories[0] ?? 'all'
  const { data } = useProjects({ category, page_size: 5 })
  const related = (data?.results ?? []).filter((p) => p.key !== project.key).slice(0, 4)
  if (!related.length) return null
  return (
    <section className="border-t border-line bg-surface-soft py-12 sm:py-14">
      <div className={WIDE}>
        <SectionHeader title={t('projects.related')} link={{ to: category === 'all' ? '/projects' : `/projects?category=${category}`, label: t('cta.allProjects') }} />
        <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {related.map((p) => <li key={p.key} className="min-w-0"><ProjectCard project={p} /></li>)}
        </ul>
      </div>
    </section>
  )
}

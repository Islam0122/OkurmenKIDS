import { CalendarDays, ExternalLink, GraduationCap, UserRound, Users } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { ButtonLink } from '@/components/shared/Button'
import { PageHero } from '@/components/shared/PageHero'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { SmartImage } from '@/components/shared/SmartImage'
import { ErrorState, NotFoundState, PageSkeleton } from '@/components/shared/States'
import { Gallery } from '@/features/content/Gallery'
import { RichText } from '@/features/content/RichText'
import { ShareButton } from '@/features/content/ShareButton'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { isNotFound, useProject } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import { excerpt } from '@/utils/format'
import { absoluteUrl, mediaUrl } from '@/utils/media'

export function ProjectDetailPage() {
  const { slug = '' } = useParams()
  const { t, path, formatDate } = useI18n()
  const { data: project, isPending, isError, error, refetch } = useProject(slug)
  if (isPending) return <PageSkeleton />
  if (isError) return isNotFound(error) ? <NotFoundState /> : <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>

  const gallery = project.images.filter((img) => img.url !== project.cover_url).map((img) => ({ url: img.url, thumb: img.url, width: null, height: null, caption: '' }))
  const author = project.student ?? t('projects.anonymous')
  return (
    <>
      <Seo
        title={project.title}
        description={project.short_description || excerpt(project.description)}
        image={project.cover_url}
        type="article"
        jsonLd={[
          breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('projects.title'), path: '/projects' }, { name: project.title, path: `/projects/${project.key}` }]),
          {
            '@context': 'https://schema.org',
            '@type': 'CreativeWork',
            name: project.title,
            description: project.short_description,
            dateCreated: project.date,
            url: absoluteUrl(path(`/projects/${project.key}`)),
            keywords: project.technologies.join(', '),
            ...(project.cover_url ? { image: absoluteUrl(mediaUrl(project.cover_url) ?? '') } : {}),
            ...(project.student ? { creator: { '@type': 'Person', name: project.student } } : {}),
            publisher: { '@type': 'EducationalOrganization', name: 'Okurmen Kids Digital' },
          },
        ]}
      />
      <PageHero title={project.title} text={project.short_description} crumbs={[{ label: t('nav.projects'), to: '/projects' }, { label: project.title }]}>
        <div className="mt-8 flex flex-wrap gap-3">
          {project.demo_url ? (
            <ButtonLink to={project.demo_url} size="lg">{t('cta.openProject')} <ExternalLink className="size-5" aria-hidden /></ButtonLink>
          ) : null}
          <ShareButton title={project.title} />
        </div>
      </PageHero>

      <div className="container-page grid gap-10 py-12 lg:grid-cols-[1fr_340px] lg:py-16">
        <div className="min-w-0 space-y-12">
          {project.cover_url ? (
            <div className="overflow-hidden rounded-[2rem] border border-line bg-surface-soft shadow-soft">
              <SmartImage src={project.cover_url} alt={project.title} priority className="w-full object-contain" />
            </div>
          ) : null}
          {project.description ? <RichText source={project.description} /> : null}
          {gallery.length ? (
            <section>
              <h2 className="mb-5 text-2xl font-black">{t('projects.gallery')}</h2>
              <Gallery photos={gallery} title={project.title} />
            </section>
          ) : null}
        </div>
        <aside className="space-y-6 lg:sticky lg:top-28 lg:self-start">
          <dl className="card divide-y divide-line">
            {[
              { icon: UserRound, label: t('projects.student'), value: author },
              project.group && { icon: Users, label: t('projects.group'), value: project.group },
              project.trainer && { icon: GraduationCap, label: t('projects.trainer'), value: project.trainer },
              { icon: CalendarDays, label: t('projects.date'), value: formatDate(project.date) },
            ].filter(Boolean).map((row) => {
              const r = row as { icon: typeof UserRound; label: string; value: string }
              return (
                <div key={r.label} className="flex items-center gap-3 p-5">
                  <r.icon className="size-5 shrink-0 text-brand-400" aria-hidden />
                  <div><dt className="text-xs font-bold text-muted uppercase">{r.label}</dt><dd className="font-bold">{r.value}</dd></div>
                </div>
              )
            })}
            {project.technologies.length ? (
              <div className="p-5">
                <dt className="mb-2 text-xs font-bold text-muted uppercase">{t('projects.technologies')}</dt>
                <dd className="flex flex-wrap gap-1.5">{project.technologies.map((tech) => <span key={tech} className="rounded-lg bg-brand-50 px-2.5 py-1 text-sm font-bold text-brand-700">{tech}</span>)}</dd>
              </div>
            ) : null}
          </dl>
          <div className="rounded-3xl bg-brand-800 p-6 text-white">
            <p className="font-display text-xl font-black text-white">{t('home.cta.title')}</p>
            <EnrollButton className="mt-5 w-full" />
          </div>
        </aside>
      </div>
    </>
  )
}

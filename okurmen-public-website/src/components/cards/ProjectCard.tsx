import { ArrowUpRight, CalendarDays, Code2, UserRound } from 'lucide-react'
import { Link } from 'react-router-dom'

import { SmartImage } from '@/components/shared/SmartImage'
import { useI18n } from '@/i18n'
import type { ProjectCard as Project } from '@/types/api'

const MAX_BADGES = 4

/**
 * A published student project (GET /api/v1/public/projects/). The whole card
 * is one link to /projects/:key; the student's name is shown only as the API
 * returns it (null when the family did not approve it).
 */
export function ProjectCard({ project }: { project: Project }) {
  const { t, path, formatDate } = useI18n()
  const badges = project.technologies.slice(0, MAX_BADGES)
  const more = project.technologies.length - badges.length
  return (
    <Link
      to={path(`/projects/${project.key}`)}
      aria-label={`${project.title} — ${t('projects.open')}`}
      className="card group flex h-full flex-col overflow-hidden transition duration-300 hover:-translate-y-1 hover:border-brand-200 hover:shadow-lift focus-visible:-translate-y-1"
    >
      <div className="relative aspect-video overflow-hidden border-b border-line bg-gradient-to-br from-brand-50 to-surface-soft">
        <SmartImage
          src={project.cover_url}
          alt=""
          sizes="(min-width: 1536px) 25vw, (min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
          className="size-full object-top transition duration-700 ease-out group-hover:scale-[1.04]"
          fallback={<Code2 className="size-12 text-brand-300" aria-hidden />}
        />
        {project.categories.length ? (
          <div className="absolute top-3 left-3 flex flex-wrap gap-1.5">
            {project.categories.map((cat) => (
              <span key={cat} className="rounded-full bg-white/95 px-2.5 py-1 text-xs font-bold text-brand-800 shadow-soft backdrop-blur">{t(`projects.cat.${cat}`)}</span>
            ))}
          </div>
        ) : null}
        <span aria-hidden className="absolute right-3 bottom-3 inline-flex translate-y-2 items-center gap-1 rounded-full bg-gold-400 px-3 py-1.5 text-xs font-bold text-brand-900 opacity-0 shadow-gold transition duration-300 group-hover:translate-y-0 group-hover:opacity-100">
          {t('projects.open')} <ArrowUpRight className="size-3.5" />
        </span>
      </div>

      <div className="flex flex-1 flex-col p-5">
        <h3 className="line-clamp-2 text-lg leading-snug font-extrabold tracking-tight transition group-hover:text-brand-600">{project.title}</h3>
        {project.short_description ? <p className="mt-1.5 line-clamp-2 min-h-12 text-sm leading-6 text-muted">{project.short_description}</p> : null}
        {badges.length ? (
          <ul className="mt-3.5 flex flex-wrap gap-1.5" aria-label={t('projects.technologies')}>
            {badges.map((tech) => (
              <li key={tech} className="rounded-md bg-surface-purple px-2 py-0.5 text-xs font-semibold text-brand-700">{tech}</li>
            ))}
            {more > 0 ? <li className="rounded-md bg-surface-soft px-2 py-0.5 text-xs font-semibold text-muted">+{more}</li> : null}
          </ul>
        ) : null}
        <div className="min-h-4 flex-1" aria-hidden />
        <div className="flex items-center justify-between gap-3 border-t border-line pt-3.5 text-sm">
          <span className="flex min-w-0 items-center gap-2 font-semibold text-ink-soft">
            <span className="grid size-7 shrink-0 place-items-center rounded-full bg-gold-100 text-gold-700"><UserRound className="size-3.5" aria-hidden /></span>
            <span className="truncate">{project.student ?? t('projects.anonymous')}</span>
          </span>
          <time dateTime={project.date} className="flex shrink-0 items-center gap-1 text-xs text-muted">
            <CalendarDays className="size-3.5" aria-hidden />
            {formatDate(project.date, { day: 'numeric', month: 'short', year: 'numeric' })}
          </time>
        </div>
      </div>
    </Link>
  )
}

import { motion } from 'framer-motion'
import { ArrowRight, CalendarDays, FolderKanban, UserRound, UsersRound } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { PublicProjectSummary } from '@/api/publicProjects'
import { cardVariants } from '@/features/portal/AppCard'
import { useI18n } from '@/features/portal/i18n'
import { resolveMediaUrl } from '@/lib/mediaUrl'

import { formatProjectDate } from './format'

const MAX_TAGS = 3

/** One project in the public gallery: cover, title, who made it, tags, date. */
export function ProjectCard({ project }: { project: PublicProjectSummary }) {
  const { t, lang } = useI18n()
  const g = t.gallery
  const cover = resolveMediaUrl(project.cover_url)
  const extra = project.technologies.length - MAX_TAGS
  const student = project.student ?? g.hiddenStudent

  return (
    <motion.li variants={cardVariants} className="min-w-0 list-none">
      <Link
        to={`/projects/${project.key}`}
        className="group flex h-full flex-col overflow-hidden rounded-2xl border border-pd-line bg-pd-panel pd-shadow outline-none transition-[border-color,box-shadow,transform] duration-300 hover:-translate-y-1 hover:border-pd-green-line hover:pd-shadow-lg focus-visible:border-pd-green focus-visible:ring-4 focus-visible:ring-pd-green/15"
        aria-label={`${project.title} — ${student}${project.group ? `, ${project.group}` : ''}`}
        data-project={project.key}
      >
        <div className="relative aspect-[16/10] overflow-hidden border-b border-pd-line bg-pd-subtle">
          {cover ? (
            <img
              src={cover}
              alt=""
              loading="lazy"
              decoding="async"
              className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
            />
          ) : (
            <div className="flex size-full items-center justify-center bg-gradient-to-br from-pd-green-soft to-white">
              <span className="grid size-14 place-items-center rounded-2xl border border-pd-green-line bg-white text-pd-green pd-shadow">
                <FolderKanban className="size-6" strokeWidth={1.75} aria-hidden />
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col p-4 sm:p-5">
          <h3 className="line-clamp-1 text-base font-bold tracking-tight">{project.title}</h3>
          <p className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs text-pd-muted">
            <span className="inline-flex min-w-0 items-center gap-1">
              <UserRound className="size-3.5 shrink-0 text-pd-green" aria-hidden />
              <span className="truncate">{student}</span>
            </span>
            {project.group ? (
              <span className="inline-flex min-w-0 items-center gap-1">
                <UsersRound className="size-3.5 shrink-0 text-pd-faint" aria-hidden />
                <span className="truncate">{project.group}</span>
              </span>
            ) : null}
          </p>
          {project.short_description ? (
            <p className="mt-2.5 line-clamp-2 text-sm leading-snug text-pd-muted">{project.short_description}</p>
          ) : null}
          {project.technologies.length > 0 ? (
            <ul className="mt-3 flex flex-wrap gap-1.5" aria-label={g.technologies}>
              {project.technologies.slice(0, MAX_TAGS).map((tech) => (
                <li key={tech} className="rounded-md border border-pd-green-line bg-pd-green-soft px-1.5 py-0.5 text-[11px] font-medium text-pd-green-deep">
                  {tech}
                </li>
              ))}
              {extra > 0 ? (
                <li className="rounded-md border border-pd-line bg-pd-subtle px-1.5 py-0.5 text-[11px] font-medium text-pd-muted">+{extra}</li>
              ) : null}
            </ul>
          ) : null}

          <div className="mt-auto flex items-center justify-between gap-3 pt-4">
            <span className="inline-flex items-center gap-1 text-xs text-pd-faint">
              <CalendarDays className="size-3.5" aria-hidden />
              <time dateTime={project.date}>{formatProjectDate(project.date, lang)}</time>
            </span>
            <span className="inline-flex items-center gap-1 text-sm font-semibold text-pd-green transition-colors group-hover:text-pd-green-deep">
              {g.view}
              <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden />
            </span>
          </div>
        </div>
      </Link>
    </motion.li>
  )
}

export function ProjectCardSkeleton() {
  return (
    <li className="list-none overflow-hidden rounded-2xl border border-pd-line bg-pd-panel pd-shadow" aria-hidden>
      <div className="aspect-[16/10] animate-pulse bg-zinc-100" />
      <div className="space-y-3 p-5">
        <div className="h-4 w-2/3 animate-pulse rounded bg-zinc-100" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-zinc-100" />
        <div className="h-3 w-full animate-pulse rounded bg-zinc-100" />
        <div className="flex gap-1.5">
          <div className="h-5 w-14 animate-pulse rounded bg-zinc-100" />
          <div className="h-5 w-12 animate-pulse rounded bg-zinc-100" />
        </div>
      </div>
    </li>
  )
}

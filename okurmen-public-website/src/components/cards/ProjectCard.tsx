import { Code2, UserRound } from 'lucide-react'
import { Link } from 'react-router-dom'

import { SmartImage } from '@/components/shared/SmartImage'
import { useI18n } from '@/i18n'
import type { ProjectCard as Project } from '@/types/api'

export function ProjectCard({ project }: { project: Project }) {
  const { t, path, formatDate } = useI18n()
  return (
    <Link to={path(`/projects/${project.key}`)} className="card card-hover group flex h-full flex-col overflow-hidden">
      <div className="relative aspect-[16/10] overflow-hidden bg-brand-50">
        <SmartImage src={project.cover_url} alt={project.title} className="size-full object-top transition duration-700 group-hover:scale-105" fallback={<Code2 className="size-12 text-brand-300" aria-hidden />} />
        <div className="absolute inset-x-0 bottom-0 flex flex-wrap gap-1.5 bg-gradient-to-t from-brand-950/70 to-transparent p-3 pt-10">
          {project.categories.map((cat) => (
            <span key={cat} className="rounded-full bg-white/90 px-2 py-0.5 text-[11px] font-bold text-brand-800">{t(`projects.cat.${cat}`)}</span>
          ))}
        </div>
      </div>
      <div className="flex flex-1 flex-col p-5">
        <h3 className="text-lg leading-snug font-extrabold">{project.title}</h3>
        {project.short_description ? <p className="mt-1.5 line-clamp-2 text-sm text-muted">{project.short_description}</p> : null}
        <div className="mt-auto flex items-center justify-between gap-3 pt-4 text-sm">
          <span className="flex min-w-0 items-center gap-2 font-semibold text-ink-soft">
            <span className="grid size-7 shrink-0 place-items-center rounded-full bg-gold-100 text-gold-700"><UserRound className="size-3.5" aria-hidden /></span>
            <span className="truncate">{project.student ?? t('projects.anonymous')}</span>
          </span>
          <time dateTime={project.date} className="shrink-0 text-xs text-muted">{formatDate(project.date, { month: 'short', year: 'numeric' })}</time>
        </div>
      </div>
    </Link>
  )
}

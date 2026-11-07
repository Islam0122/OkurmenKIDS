import { ArrowRight, CalendarDays, Images, Pencil, Trash2, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Menu } from '@/components/ui/Menu'
import type { MenuItem } from '@/components/ui/Menu'
import type { ProjectListItem } from '@/types/projects'
import { formatDate } from '@/utils/format'
import { cn } from '@/utils/cn'

import { Avatar, ProjectCover, RatingStars, StatusPill, TechTag } from './shared'

export interface ProjectCardProps {
  project: ProjectListItem
  base: string
  onEdit: (project: ProjectListItem) => void
  onDelete: (project: ProjectListItem) => void
}

function menuItems({ project, onEdit, onDelete }: ProjectCardProps): MenuItem[] {
  if (!project.can_edit) return []
  return [
    { key: 'edit', label: 'Редактировать', icon: <Pencil className="size-4" aria-hidden />, onClick: () => onEdit(project) },
    { key: 'delete', label: 'Удалить', tone: 'danger', icon: <Trash2 className="size-4" aria-hidden />, onClick: () => onDelete(project) },
  ]
}

function Tags({ names, max }: { names: string[]; max: number }) {
  if (names.length === 0) return null
  const shown = names.slice(0, max)
  return (
    <div className="flex flex-wrap gap-1.5">
      {shown.map((name) => <TechTag key={name} name={name} />)}
      {names.length > max ? <TechTag name={`+${names.length - max}`} className="text-ink-muted" /> : null}
    </div>
  )
}

/** Gallery card. The whole card is one link (via the title's stretched
 * ::after), so it is a single tab stop; the ⋯ menu sits above it. */
export function ProjectCard(props: ProjectCardProps) {
  const { project, base } = props
  const href = `${base}/${project.id}`
  return (
    <article className="group card relative flex min-w-0 flex-col overflow-hidden transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-[0_12px_32px_-12px_rgba(31,95,60,0.22)] focus-within:border-brand-200">
      <div className="relative">
        <ProjectCover
          url={project.cover_url}
          title={project.title}
          className="aspect-[16/10]"
          imgClassName="transition-transform duration-500 ease-out group-hover:scale-[1.03]"
        />
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-3">
          {project.status === 'draft' ? <StatusPill status="draft" className="bg-surface/95 backdrop-blur" /> : <span />}
          {project.images_count > 1 ? (
            <span className="inline-flex h-6 items-center gap-1 rounded-full bg-ink/55 px-2 text-xs font-medium text-white backdrop-blur">
              <Images className="size-3.5" aria-hidden />
              {project.images_count}
            </span>
          ) : null}
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="min-w-0 text-[15px] font-semibold leading-snug text-ink">
            <Link to={href} className="line-clamp-2 outline-none after:absolute after:inset-0 after:content-[''] focus-visible:underline">
              {project.title}
            </Link>
          </h3>
          <div className="relative z-10 -mr-1 -mt-1">
            <Menu items={menuItems(props)} label={`Действия с проектом «${project.title}»`} />
          </div>
        </div>

        <div className="flex min-w-0 items-center gap-2.5">
          <Avatar name={project.student.full_name} seed={project.student.id} size="sm" />
          <div className="min-w-0 text-sm">
            <p className="truncate font-medium text-ink">{project.student.full_name}</p>
            <p className="flex items-center gap-2 truncate text-xs text-ink-muted">
              {project.group ? (
                <span className="inline-flex min-w-0 items-center gap-1"><Users className="size-3 shrink-0" aria-hidden /><span className="truncate">{project.group.name}</span></span>
              ) : null}
              <span className="inline-flex shrink-0 items-center gap-1"><CalendarDays className="size-3" aria-hidden />{formatDate(project.project_date)}</span>
            </p>
          </div>
        </div>

        {project.short_description ? <p className="line-clamp-2 text-sm text-ink-secondary">{project.short_description}</p> : null}

        <div className="mt-auto space-y-3">
          <Tags names={project.technologies} max={3} />
          <div className="flex items-center justify-between border-t border-border pt-3">
            {project.rating ? <RatingStars value={project.rating} /> : <span className="text-xs text-ink-muted">Без оценки</span>}
            <span className="inline-flex items-center gap-1 text-sm font-medium text-brand-700">
              Подробнее
              <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden />
            </span>
          </div>
        </div>
      </div>
    </article>
  )
}

/** List view row: thumbnail, title + student, group/date, tags, actions. */
export function ProjectRow(props: ProjectCardProps) {
  const { project, base } = props
  return (
    <li className="group relative flex items-center gap-3 px-3 py-3 transition-colors hover:bg-surface-hover/60 sm:gap-4 sm:px-4">
      <ProjectCover url={project.cover_url} title={project.title} className="h-14 w-20 shrink-0 rounded-lg ring-1 ring-border sm:h-16 sm:w-24" />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <Link
            to={`${base}/${project.id}`}
            className="truncate text-sm font-semibold text-ink outline-none after:absolute after:inset-0 after:content-[''] hover:text-brand-700 focus-visible:underline"
          >
            {project.title}
          </Link>
          {project.status === 'draft' ? <StatusPill status="draft" className="hidden sm:inline-flex" /> : null}
        </div>
        <p className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs text-ink-secondary">
          <Avatar name={project.student.full_name} seed={project.student.id} size="xs" />
          <span className="truncate">{project.student.full_name}</span>
          {project.group ? <span className="hidden truncate text-ink-muted sm:inline">· {project.group.name}</span> : null}
        </p>
      </div>
      <div className="hidden min-w-0 max-w-[16rem] lg:block">
        <Tags names={project.technologies} max={3} />
      </div>
      <p className={cn('hidden w-32 shrink-0 text-right text-xs text-ink-muted md:block')}>{formatDate(project.project_date)}</p>
      <div className="relative z-10 shrink-0">
        <Menu items={menuItems(props)} label={`Действия с проектом «${project.title}»`} />
      </div>
    </li>
  )
}

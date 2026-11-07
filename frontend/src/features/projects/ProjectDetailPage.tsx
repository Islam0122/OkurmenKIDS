import { useState } from 'react'
import type { ReactNode } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight, ExternalLink, Figma, Github, Globe, Layers, Pencil, Quote, Trash2, Users } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ErrorState } from '@/components/ui/ErrorState'
import { Menu } from '@/components/ui/Menu'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { useDeleteProject, useProject } from '@/hooks/useProjects'
import { extractErrorMessage } from '@/lib/apiError'
import { resolveMediaUrl } from '@/lib/mediaUrl'
import type { ProjectDetail } from '@/types/projects'
import { formatDate } from '@/utils/format'
import { cn } from '@/utils/cn'

import { Avatar, CoverPlaceholder, RatingStars, StatusPill, TechTag, useProjectsBase } from './shared'

const STUDENT_STATUS: Record<string, string> = {
  active: 'Учится', paused: 'На паузе', completed: 'Завершил обучение', withdrawn: 'Не учится',
}

function SideCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card card-body">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-muted">{title}</h2>
      {children}
    </section>
  )
}

function InfoRow({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
      <span className="mt-0.5 text-ink-muted">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs text-ink-muted">{label}</p>
        <div className="text-sm font-medium text-ink">{children}</div>
      </div>
    </div>
  )
}

function LinkButton({ href, icon, label }: { href: string; icon: ReactNode; label: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer"
      className="group inline-flex h-11 items-center gap-2.5 rounded-lg border border-border bg-surface px-4 text-sm font-medium text-ink transition-colors hover:border-brand-200 hover:bg-brand-50/50 hover:text-brand-700">
      {icon}
      {label}
      <ExternalLink className="size-3.5 text-ink-muted transition-transform group-hover:-translate-y-px group-hover:translate-x-px" aria-hidden />
    </a>
  )
}

function Gallery({ project }: { project: ProjectDetail }) {
  const images = project.images.filter((img) => img.url)
  const coverIndex = Math.max(0, images.findIndex((img) => img.is_cover))
  const [index, setIndex] = useState(coverIndex)
  const [zoom, setZoom] = useState(false)
  const current = images[index] ?? images[0]
  const go = (delta: number) => setIndex((n) => (n + delta + images.length) % images.length)

  if (!current) {
    return <div className="card aspect-[16/9] overflow-hidden"><CoverPlaceholder title={project.title} /></div>
  }
  const src = resolveMediaUrl(current.url) ?? ''
  return (
    <div className="space-y-3">
      <div className="card group relative overflow-hidden bg-surface-muted">
        <button type="button" onClick={() => setZoom(true)} className="block aspect-[16/9] w-full cursor-zoom-in" aria-label="Открыть изображение крупно">
          <img src={src} alt={`«${project.title}» — изображение ${index + 1} из ${images.length}`} className="size-full object-cover" />
        </button>
        {images.length > 1 ? (
          <>
            <button type="button" onClick={() => go(-1)} aria-label="Предыдущее изображение"
              className="absolute left-3 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full bg-surface/90 text-ink shadow-md backdrop-blur transition-opacity hover:bg-surface sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100">
              <ChevronLeft className="size-5" aria-hidden />
            </button>
            <button type="button" onClick={() => go(1)} aria-label="Следующее изображение"
              className="absolute right-3 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full bg-surface/90 text-ink shadow-md backdrop-blur transition-opacity hover:bg-surface sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100">
              <ChevronRight className="size-5" aria-hidden />
            </button>
            <span className="absolute bottom-3 right-3 rounded-full bg-ink/60 px-2.5 py-1 text-xs font-medium text-white backdrop-blur">{index + 1} / {images.length}</span>
          </>
        ) : null}
      </div>
      {images.length > 1 ? (
        <div className="scroll-x flex gap-2 pb-1" role="tablist" aria-label="Галерея">
          {images.map((img, n) => (
            <button key={img.id} type="button" role="tab" aria-selected={n === index} aria-label={`Изображение ${n + 1}`} onClick={() => setIndex(n)}
              className={cn('h-16 w-24 shrink-0 overflow-hidden rounded-lg border-2 transition-all',
                n === index ? 'border-brand-500' : 'border-transparent opacity-70 hover:opacity-100')}>
              <img src={resolveMediaUrl(img.url) ?? ''} alt="" className="size-full object-cover" />
            </button>
          ))}
        </div>
      ) : null}
      <Modal isOpen={zoom} onClose={() => setZoom(false)} title={project.title} size="xl">
        <img src={src} alt={`«${project.title}» — изображение ${index + 1}`} className="mx-auto max-h-[75dvh] w-auto rounded-lg object-contain" />
      </Modal>
    </div>
  )
}

export function ProjectDetailPage() {
  const base = useProjectsBase()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const id = Number(useParams().id)
  const { data: project, isPending, isError, refetch } = useProject(id)
  const remove = useDeleteProject()
  const [confirming, setConfirming] = useState(false)

  if (isPending) {
    return (
      <div className="animate-pulse" role="status" aria-label="Загружаем проект…">
        <div className="mb-4 h-4 w-32 rounded bg-surface-hover" />
        <div className="mb-6 h-7 w-1/2 rounded bg-surface-hover" />
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="card aspect-[16/9]" />
          <div className="space-y-4"><div className="card h-40" /><div className="card h-56" /></div>
        </div>
      </div>
    )
  }
  if (isError || !project) {
    return (
      <div>
        <BackLink to={base}>Проекты студентов</BackLink>
        <ErrorState title="Проект не найден" message="Возможно, он удалён или у вас нет к нему доступа." onRetry={() => void refetch()} />
      </div>
    )
  }

  const confirmDelete = () => remove.mutate(project.id, {
    onSuccess: () => {
      showToast(`Проект «${project.title}» удалён`, 'success')
      navigate(base, { replace: true })
    },
    onError: (error) => showToast(extractErrorMessage(error, 'Не удалось удалить проект.'), 'error'),
  })

  const links = [
    project.github_url && { href: project.github_url, icon: <Github className="size-4" aria-hidden />, label: 'Код на GitHub' },
    project.demo_url && { href: project.demo_url, icon: <Globe className="size-4" aria-hidden />, label: 'Открыть демо' },
    project.figma_url && { href: project.figma_url, icon: <Figma className="size-4" aria-hidden />, label: 'Макет в Figma' },
  ].filter(Boolean) as { href: string; icon: ReactNode; label: string }[]

  return (
    <div>
      <BackLink to={base}>Проекты студентов</BackLink>

      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <h1 className="min-w-0 text-xl font-semibold text-ink sm:text-2xl">{project.title}</h1>
            <StatusPill status={project.status} />
          </div>
          {project.short_description ? <p className="mt-1.5 max-w-2xl text-sm text-ink-secondary sm:text-[15px]">{project.short_description}</p> : null}
        </div>
        {project.can_edit ? (
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="secondary" leftIcon={<Pencil className="size-4" aria-hidden />} onClick={() => navigate(`${base}/${project.id}/edit`)}>
              Редактировать
            </Button>
            <Menu items={[{ key: 'delete', label: 'Удалить проект', tone: 'danger', icon: <Trash2 className="size-4" aria-hidden />, onClick: () => setConfirming(true) }]} />
          </div>
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-6">
          <Gallery project={project} />

          {project.description ? (
            <section className="card card-body">
              <h2 className="section-title mb-3">О проекте</h2>
              <p className="whitespace-pre-line text-[15px] leading-relaxed text-ink-secondary">{project.description}</p>
            </section>
          ) : null}

          {project.technologies.length > 0 || links.length > 0 ? (
            <section className="card card-body space-y-5">
              {project.technologies.length > 0 ? (
                <div>
                  <h2 className="section-title mb-3 flex items-center gap-2"><Layers className="size-4 text-ink-muted" aria-hidden />Технологии</h2>
                  <div className="flex flex-wrap gap-2">
                    {project.technologies.map((name) => <TechTag key={name} name={name} className="h-7 px-2.5 text-sm" />)}
                  </div>
                </div>
              ) : null}
              {links.length > 0 ? (
                <div>
                  <h2 className="section-title mb-3">Ссылки</h2>
                  <div className="flex flex-wrap gap-2">{links.map((link) => <LinkButton key={link.href} {...link} />)}</div>
                </div>
              ) : null}
            </section>
          ) : null}
        </div>

        <aside className="space-y-4">
          <SideCard title="Студент">
            <div className="flex items-center gap-3">
              <Avatar name={project.student.full_name} seed={project.student.id} size="lg" />
              <div className="min-w-0">
                <p className="truncate text-base font-semibold text-ink">{project.student.full_name}</p>
                <p className="text-sm text-ink-secondary">{STUDENT_STATUS[project.student.status] ?? project.student.status}</p>
              </div>
            </div>
          </SideCard>

          <SideCard title="Информация">
            <div className="divide-y divide-border">
              <InfoRow icon={<Users className="size-4" aria-hidden />} label="Группа">
                {project.group?.name ?? '—'}
                {project.course ? <span className="block text-xs font-normal text-ink-muted">{project.course.name}</span> : null}
              </InfoRow>
              <InfoRow icon={<CalendarDays className="size-4" aria-hidden />} label="Дата проекта">{formatDate(project.project_date)}</InfoRow>
              {project.author ? (
                <InfoRow icon={<Avatar name={project.author.full_name} image={project.author.image} seed={project.author.id} size="xs" className="-ml-1" />} label="Тренер">
                  {project.author.full_name}
                </InfoRow>
              ) : null}
            </div>
          </SideCard>

          <SideCard title="Отзыв тренера">
            <div className="mb-3 flex items-center justify-between gap-2">
              {project.rating ? <RatingStars value={project.rating} size="md" /> : <span className="text-sm text-ink-muted">Без оценки</span>}
              {project.rating ? <span className="text-sm font-semibold tabular-nums text-ink">{project.rating}.0</span> : null}
            </div>
            {project.trainer_comment ? (
              <blockquote className="relative rounded-lg bg-surface-muted px-4 py-3 text-sm leading-relaxed text-ink-secondary">
                <Quote className="absolute -top-2 left-3 size-4 rotate-180 fill-brand-200 text-brand-200" aria-hidden />
                <p className="whitespace-pre-line">{project.trainer_comment}</p>
              </blockquote>
            ) : <p className="text-sm text-ink-muted">Тренер не оставил комментарий.</p>}
          </SideCard>

          <SideCard title="Публикация">
            <div className="flex items-center justify-between gap-2">
              <StatusPill status={project.status} />
              <span className="text-xs text-ink-muted">обновлён {formatDate(project.updated_at.slice(0, 10))}</span>
            </div>
            <p className="mt-2 text-xs text-ink-secondary">
              {project.status === 'published' ? 'Проект виден Team Lead, руководству и тренерам группы.' : 'Черновик виден только тренеру, который его добавил.'}
            </p>
          </SideCard>
        </aside>
      </div>

      <ConfirmDialog
        isOpen={confirming}
        title="Удалить проект?"
        message={`Проект «${project.title}» и все его изображения будут удалены без возможности восстановления.`}
        confirmLabel="Удалить"
        tone="danger"
        isLoading={remove.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setConfirming(false)}
      />
    </div>
  )
}

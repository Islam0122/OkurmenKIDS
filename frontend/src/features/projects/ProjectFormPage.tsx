import { useEffect, useId, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { isAxiosError } from 'axios'
import { format } from 'date-fns'
import { CircleCheck, FileText, Github, Globe, ImageIcon, Link2, MessageSquareQuote, Send, UserRound } from 'lucide-react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { projectsApi } from '@/api/projects'
import { useInvalidateProjects, useProject, useProjectOptions } from '@/hooks/useProjects'
import { extractErrorMessage } from '@/lib/apiError'
import type { ProjectDetail, ProjectInput, ProjectStatus } from '@/types/projects'
import { cn } from '@/utils/cn'

import { ImageDropzone, nextImageKey } from './ImageDropzone'
import type { FormImage } from './ImageDropzone'
import { ProjectCard } from './ProjectCard'
import { RatingInput } from './RatingInput'
import { StudentCombobox } from './StudentCombobox'
import { TechTagsInput } from './TechTagsInput'
import { useProjectsBase } from './shared'

interface FormState {
  student: number | null
  title: string
  short_description: string
  description: string
  technologies: string[]
  project_date: string
  github_url: string
  demo_url: string
  figma_url: string
  trainer_comment: string
  rating: number | null
  status: ProjectStatus
}

type Errors = Partial<Record<keyof FormState | 'images', string>>

const EMPTY: FormState = {
  student: null, title: '', short_description: '', description: '', technologies: [],
  project_date: format(new Date(), 'yyyy-MM-dd'), github_url: '', demo_url: '', figma_url: '',
  trainer_comment: '', rating: null, status: 'published',
}

function fromProject(p: ProjectDetail): FormState {
  return {
    student: p.student.id, title: p.title, short_description: p.short_description, description: p.description,
    technologies: p.technologies, project_date: p.project_date, github_url: p.github_url, demo_url: p.demo_url,
    figma_url: p.figma_url, trainer_comment: p.trainer_comment, rating: p.rating, status: p.status,
  }
}

function isUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

function validate(form: FormState): Errors {
  const errors: Errors = {}
  if (!form.student) errors.student = 'Выберите студента.'
  if (!form.title.trim()) errors.title = 'Укажите название проекта.'
  else if (form.title.trim().length > 150) errors.title = 'Не длиннее 150 символов.'
  if (form.short_description.length > 300) errors.short_description = 'Не длиннее 300 символов.'
  if (!form.project_date) errors.project_date = 'Укажите дату проекта.'
  for (const key of ['github_url', 'demo_url', 'figma_url'] as const) {
    if (form[key].trim() && !isUrl(form[key].trim())) errors[key] = 'Введите ссылку, начинающуюся с https://'
  }
  if (!errors.github_url && form.github_url.trim() && !/github\.com/i.test(form.github_url)) errors.github_url = 'Ссылка должна вести на github.com'
  if (!errors.figma_url && form.figma_url.trim() && !/figma\.com/i.test(form.figma_url)) errors.figma_url = 'Ссылка должна вести на figma.com'
  return errors
}

/** DRF `{field: [msg]}` → per-field messages; anything else → one line. */
function serverErrors(error: unknown): { fields: Errors; message: string } {
  const fields: Errors = {}
  if (isAxiosError(error) && error.response?.status === 400 && error.response.data && typeof error.response.data === 'object') {
    for (const [key, value] of Object.entries(error.response.data as Record<string, unknown>)) {
      fields[key as keyof Errors] = Array.isArray(value) ? value.join(' ') : String(value)
    }
  }
  return { fields, message: extractErrorMessage(error, 'Не удалось сохранить проект.') }
}

function Section({ step, icon, title, description, children }: { step: string; icon: ReactNode; title: string; description: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="card">
      <header className="flex items-start gap-3 rounded-t-xl border-b border-border bg-surface-muted/50 px-4 py-4 sm:px-6">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface text-brand-600 ring-1 ring-border">{icon}</span>
        <div className="min-w-0">
          <h2 id={id} className="flex items-center gap-2 text-[15px] font-semibold text-ink">
            <span className="text-xs font-semibold text-ink-muted">{step}</span>
            {title}
          </h2>
          <p className="mt-0.5 text-sm text-ink-secondary">{description}</p>
        </div>
      </header>
      <div className="space-y-5 px-4 py-5 sm:px-6">{children}</div>
    </section>
  )
}

function Field({ label, htmlFor, required, hint, error, counter, children, className }: {
  label: string; htmlFor?: string; required?: boolean; hint?: string; error?: string; counter?: string; children: ReactNode; className?: string
}) {
  return (
    <div className={cn('min-w-0', className)}>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
          {label}
          {required ? <span className="ml-0.5 text-danger" aria-hidden>*</span> : <span className="ml-1.5 text-xs font-normal text-ink-muted">необязательно</span>}
        </label>
        {counter ? <span className="text-xs tabular-nums text-ink-muted">{counter}</span> : null}
      </div>
      {children}
      {error ? (
        <p id={htmlFor ? `${htmlFor}-error` : undefined} role="alert" className="mt-1.5 text-xs font-medium text-danger">{error}</p>
      ) : hint ? <p className="mt-1.5 text-xs text-ink-muted">{hint}</p> : null}
    </div>
  )
}

function UrlInput({ id, icon, value, onChange, placeholder, invalid }: { id: string; icon: ReactNode; value: string; onChange: (v: string) => void; placeholder: string; invalid?: boolean }) {
  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted">{icon}</span>
      <Input id={id} type="url" inputMode="url" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)}
        aria-invalid={invalid || undefined} aria-describedby={invalid ? `${id}-error` : undefined}
        className={cn('pl-9', invalid && 'border-danger')} />
    </div>
  )
}

function StatusChoice({ value, onChange }: { value: ProjectStatus; onChange: (s: ProjectStatus) => void }) {
  const options: { value: ProjectStatus; title: string; text: string }[] = [
    { value: 'published', title: 'Опубликован', text: 'Виден Team Lead, руководству и коллегам по группе.' },
    { value: 'draft', title: 'Черновик', text: 'Виден только вам — можно дописать позже.' },
  ]
  return (
    <div role="radiogroup" aria-label="Статус проекта" className="grid gap-2 sm:grid-cols-2">
      {options.map((option) => {
        const active = option.value === value
        return (
          <button key={option.value} type="button" role="radio" aria-checked={active} onClick={() => onChange(option.value)}
            className={cn('flex items-start gap-3 rounded-xl border p-3.5 text-left transition-colors',
              active ? 'border-brand-500 bg-brand-50/60 ring-2 ring-brand-500/15' : 'border-border hover:border-brand-200 hover:bg-surface-hover')}>
            <span className={cn('mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border-2', active ? 'border-brand-500' : 'border-border-strong')}>
              {active ? <span className="size-2 rounded-full bg-brand-500" /> : null}
            </span>
            <span>
              <span className="block text-sm font-medium text-ink">{option.title}</span>
              <span className="mt-0.5 block text-xs text-ink-secondary">{option.text}</span>
            </span>
          </button>
        )
      })}
    </div>
  )
}

export function ProjectFormPage() {
  const base = useProjectsBase()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const invalidate = useInvalidateProjects()
  const params = useParams()
  const [search] = useSearchParams()
  const editId = params.id ? Number(params.id) : undefined
  const isEdit = editId !== undefined

  const options = useProjectOptions()
  const existing = useProject(editId)

  const [form, setForm] = useState<FormState>(() => ({ ...EMPTY, student: Number(search.get('student')) || null }))
  const [images, setImages] = useState<FormImage[]>([])
  const [removedIds, setRemovedIds] = useState<number[]>([])
  const [errors, setErrors] = useState<Errors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState<ProjectStatus | null>(null)
  // After a create whose uploads partly failed, a retry updates that project instead of creating a second one.
  const [projectId, setProjectId] = useState<number | undefined>(editId)
  const [loadedFrom, setLoadedFrom] = useState<number | null>(null)

  useEffect(() => {
    const p = existing.data
    if (!p || loadedFrom === p.id) return
    setForm(fromProject(p))
    setImages(p.images.map((img) => ({ key: nextImageKey(), kind: 'existing', id: img.id, url: img.url, isCover: img.is_cover })))
    setLoadedFrom(p.id)
  }, [existing.data, loadedFrom])

  const students = options.data?.selectable_students ?? []
  // Admin editing someone's project: the current student may be outside the selectable list.
  const studentChoices = useMemo(() => {
    const p = existing.data
    if (p && !students.some((s) => s.id === p.student.id)) {
      return [{ id: p.student.id, full_name: p.student.full_name, status: p.student.status, group: p.group, projects_count: 0 }, ...students]
    }
    return students
  }, [students, existing.data])
  const selectedStudent = studentChoices.find((s) => s.id === form.student) ?? null

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    if (errors[key]) setErrors((e) => ({ ...e, [key]: undefined }))
  }

  const changeImages = (next: FormImage[]) => {
    const keep = new Set(next.map((i) => i.key))
    const dropped = images.filter((i) => i.kind === 'existing' && !keep.has(i.key)).map((i) => (i as { id: number }).id)
    if (dropped.length) setRemovedIds((ids) => [...ids, ...dropped])
    setImages(next)
  }

  const patchImage = (key: string, patch: Partial<Extract<FormImage, { kind: 'new' }>>) =>
    setImages((list) => list.map((img) => (img.key === key && img.kind === 'new' ? { ...img, ...patch } : img)))

  const submit = async (status: ProjectStatus) => {
    const next = { ...form, status }
    setForm(next)
    setFormError(null)
    const found = validate(next)
    setErrors(found)
    if (Object.keys(found).length > 0) {
      setFormError('Проверьте выделенные поля.')
      document.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()
      return
    }
    setSaving(status)
    const body: ProjectInput = {
      ...next,
      student: next.student as number,
      title: next.title.trim(),
      github_url: next.github_url.trim(),
      demo_url: next.demo_url.trim(),
      figma_url: next.figma_url.trim(),
    }
    let id = projectId
    try {
      const saved = id ? await projectsApi.update(id, body) : await projectsApi.create(body)
      id = saved.id
      setProjectId(id)
    } catch (error) {
      const { fields, message } = serverErrors(error)
      setErrors(fields)
      setFormError(Object.keys(fields).length ? 'Проверьте выделенные поля.' : message)
      setSaving(null)
      return
    }

    // Images: removals, then uploads one by one (each with its own progress), then the cover.
    let failed = 0
    for (const imageId of removedIds) {
      try { await projectsApi.removeImage(id, imageId) } catch { /* already gone */ }
    }
    setRemovedIds([])
    const uploaded = new Map<string, number>()
    for (const img of images) {
      if (img.kind !== 'new') continue
      patchImage(img.key, { progress: 0, error: null })
      try {
        const result = await projectsApi.uploadImage(id, img.file, img.isCover, (p) => patchImage(img.key, { progress: p }))
        uploaded.set(img.key, result.id)
        patchImage(img.key, { progress: 100 })
      } catch (error) {
        failed += 1
        patchImage(img.key, { progress: null, error: extractErrorMessage(error, 'Не удалось загрузить') })
      }
    }
    // Uploaded files become server images; failed ones stay for a retry.
    setImages((list) => list.map((img) => {
      const newId = uploaded.get(img.key)
      return newId && img.kind === 'new' ? { key: img.key, kind: 'existing', id: newId, url: img.previewUrl, isCover: img.isCover } : img
    }))
    const cover = images.find((img) => img.isCover)
    const coverId = cover ? (cover.kind === 'existing' ? cover.id : uploaded.get(cover.key)) : undefined
    if (coverId && cover?.kind === 'existing') {
      try { await projectsApi.setCover(id, coverId) } catch { failed += 1 }
    }

    await invalidate()
    setSaving(null)
    if (failed > 0) {
      setFormError(`Проект сохранён, но ${failed} изображ. не загрузились. Удалите их или нажмите «Сохранить» ещё раз.`)
      showToast('Проект сохранён, но часть изображений не загрузилась', 'error')
      return
    }
    showToast(status === 'published' ? 'Проект опубликован' : 'Черновик сохранён', 'success')
    navigate(`${base}/${id}`)
  }

  if (isEdit && existing.isPending) return <LoadingState label="Загружаем проект…" />
  if (isEdit && existing.isError) return <ErrorState title="Проект не найден" message="Возможно, он удалён или у вас нет к нему доступа." onRetry={() => void existing.refetch()} />
  if (isEdit && existing.data && !existing.data.can_edit) {
    return <ErrorState title="Нет доступа" message="Изменять проект может только тренер, который его добавил." />
  }
  if (!isEdit && options.data && !options.data.can_create) {
    return <ErrorState title="Добавлять проекты может только тренер" message="Студенты показывают работы своему тренеру — он и добавляет их в LMS." />
  }

  const busy = saving !== null
  const preview = {
    id: projectId ?? 0,
    title: form.title.trim() || 'Название проекта',
    short_description: form.short_description || 'Краткое описание появится здесь.',
    project_date: form.project_date || format(new Date(), 'yyyy-MM-dd'),
    status: form.status,
    rating: form.rating,
    technologies: form.technologies,
    student: { id: selectedStudent?.id ?? 0, full_name: selectedStudent?.full_name ?? 'Студент', status: 'active' },
    group: selectedStudent?.group ?? null,
    author: null,
    cover_url: (() => {
      const cover = images.find((i) => i.isCover) ?? images[0]
      return cover ? (cover.kind === 'new' ? cover.previewUrl : cover.url) : null
    })(),
    images_count: images.length,
    can_edit: false,
    created_at: '',
    updated_at: '',
  }
  const checklist = [
    { done: Boolean(form.student), label: 'Студент выбран' },
    { done: Boolean(form.title.trim()), label: 'Есть название' },
    { done: images.length > 0, label: 'Добавлены изображения' },
    { done: form.technologies.length > 0, label: 'Указаны технологии' },
    { done: Boolean(form.github_url || form.demo_url), label: 'Есть ссылка на код или демо' },
  ]

  return (
    <div>
      <BackLink to={isEdit ? `${base}/${editId}` : base}>{isEdit ? 'К проекту' : 'Проекты студентов'}</BackLink>
      <PageHeader
        title={isEdit ? 'Редактирование проекта' : 'Новый проект'}
        description={isEdit ? existing.data?.title : 'Студент показал работу — зарегистрируйте её в портфолио группы.'}
      />

      <form noValidate onSubmit={(event) => { event.preventDefault(); void submit(form.status) }}>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-5">
            <Section step="01" icon={<UserRound className="size-[18px]" aria-hidden />} title="Студент" description="Чья это работа и когда она была представлена.">
              <Field label="Студент" htmlFor="project-student" required error={errors.student}
                hint={students.length === 0 && options.data ? 'В ваших группах пока нет студентов.' : 'Поиск по имени или названию группы.'}>
                <StudentCombobox id="project-student" students={studentChoices} value={form.student} onChange={(v) => set('student', v)}
                  invalid={Boolean(errors.student)} isLoading={options.isPending} />
              </Field>
              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="Группа" htmlFor="project-group" required hint="Определяется по студенту автоматически.">
                  <Input id="project-group" readOnly value={selectedStudent?.group?.name ?? ''} placeholder="Выберите студента" className="bg-surface-muted text-ink-secondary" />
                </Field>
                <Field label="Дата проекта" htmlFor="project-date" required error={errors.project_date}>
                  <DatePicker id="project-date" value={form.project_date} max={format(new Date(), 'yyyy-MM-dd')}
                    onChange={(e) => set('project_date', e.target.value)} aria-invalid={Boolean(errors.project_date) || undefined} />
                </Field>
              </div>
            </Section>

            <Section step="02" icon={<FileText className="size-[18px]" aria-hidden />} title="О проекте" description="Название, описание и технологии, на которых он сделан.">
              <Field label="Название проекта" htmlFor="project-title" required error={errors.title} counter={`${form.title.length}/150`}>
                <Input id="project-title" value={form.title} maxLength={150} placeholder="Например, «Приложение погоды»"
                  onChange={(e) => set('title', e.target.value)} aria-invalid={Boolean(errors.title) || undefined}
                  aria-describedby={errors.title ? 'project-title-error' : undefined} className={cn(errors.title && 'border-danger')} />
              </Field>
              <Field label="Краткое описание" htmlFor="project-short" error={errors.short_description} counter={`${form.short_description.length}/300`}
                hint="Одно-два предложения — показываются на карточке.">
                <Textarea id="project-short" rows={2} maxLength={300} value={form.short_description}
                  placeholder="Что делает проект и чем он интересен" onChange={(e) => set('short_description', e.target.value)} />
              </Field>
              <Field label="Полное описание" htmlFor="project-description" error={errors.description}
                hint="Идея, функции, что было сложным и чему студент научился.">
                <Textarea id="project-description" rows={6} value={form.description} onChange={(e) => set('description', e.target.value)} />
              </Field>
              <Field label="Технологии" htmlFor="project-tech" error={errors.technologies}>
                <TechTagsInput id="project-tech" value={form.technologies} onChange={(v) => set('technologies', v)} suggestions={options.data?.technologies} />
              </Field>
            </Section>

            <Section step="03" icon={<ImageIcon className="size-[18px]" aria-hidden />} title="Изображения" description="Скриншоты и фото работы. Отмеченное звездой — обложка карточки.">
              <ImageDropzone images={images} onChange={changeImages} max={options.data?.max_images ?? 12} disabled={busy} />
            </Section>

            <Section step="04" icon={<Link2 className="size-[18px]" aria-hidden />} title="Ссылки" description="Где посмотреть код и готовый проект.">
              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="Репозиторий GitHub" htmlFor="project-github" error={errors.github_url}>
                  <UrlInput id="project-github" icon={<Github className="size-4" aria-hidden />} value={form.github_url} onChange={(v) => set('github_url', v)}
                    placeholder="https://github.com/…" invalid={Boolean(errors.github_url)} />
                </Field>
                <Field label="Демо" htmlFor="project-demo" error={errors.demo_url}>
                  <UrlInput id="project-demo" icon={<Globe className="size-4" aria-hidden />} value={form.demo_url} onChange={(v) => set('demo_url', v)}
                    placeholder="https://…" invalid={Boolean(errors.demo_url)} />
                </Field>
                <Field label="Макет в Figma" htmlFor="project-figma" error={errors.figma_url} className="sm:col-span-2">
                  <UrlInput id="project-figma" icon={<Link2 className="size-4" aria-hidden />} value={form.figma_url} onChange={(v) => set('figma_url', v)}
                    placeholder="https://www.figma.com/…" invalid={Boolean(errors.figma_url)} />
                </Field>
              </div>
            </Section>

            <Section step="05" icon={<MessageSquareQuote className="size-[18px]" aria-hidden />} title="Отзыв тренера" description="Ваша оценка работы и статус публикации.">
              <Field label="Комментарий тренера" htmlFor="project-comment" error={errors.trainer_comment} hint="Что получилось особенно хорошо и над чем поработать дальше.">
                <Textarea id="project-comment" rows={4} value={form.trainer_comment} onChange={(e) => set('trainer_comment', e.target.value)} />
              </Field>
              <Field label="Оценка" error={errors.rating}>
                <RatingInput value={form.rating} onChange={(v) => set('rating', v)} />
              </Field>
              <Field label="Статус" required>
                <StatusChoice value={form.status} onChange={(v) => set('status', v)} />
              </Field>
            </Section>
          </div>

          <aside className="hidden lg:block">
            <div className="sticky top-[calc(var(--spacing-header)+1.5rem)] space-y-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Предпросмотр карточки</p>
              <div className="pointer-events-none select-none" aria-hidden>
                <ProjectCard project={preview} base={base} onEdit={() => undefined} onDelete={() => undefined} />
              </div>
              <div className="card card-body">
                <p className="mb-3 text-sm font-medium text-ink">Готовность</p>
                <ul className="space-y-2">
                  {checklist.map((item) => (
                    <li key={item.label} className={cn('flex items-center gap-2 text-sm', item.done ? 'text-ink' : 'text-ink-muted')}>
                      <CircleCheck className={cn('size-4 shrink-0', item.done ? 'text-brand-500' : 'text-border-strong')} aria-hidden />
                      {item.label}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </aside>
        </div>

        <div className="sticky bottom-[calc(var(--spacing-mobile-nav)+env(safe-area-inset-bottom))] z-20 -mx-4 mt-6 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6 lg:bottom-0 lg:-mx-8 lg:px-8">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className={cn('min-h-5 text-sm', formError ? 'font-medium text-danger' : 'text-ink-muted')} role={formError ? 'alert' : undefined}>
              {formError ?? (busy ? 'Сохраняем проект…' : 'Поля со * обязательны.')}
            </p>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button type="button" variant="ghost" disabled={busy} onClick={() => navigate(isEdit ? `${base}/${editId}` : base)}>Отмена</Button>
              <Button type="button" variant="secondary" isLoading={saving === 'draft'} disabled={busy} onClick={() => void submit('draft')}>
                Сохранить черновик
              </Button>
              <Button type="button" isLoading={saving === 'published'} disabled={busy} leftIcon={<Send className="size-4" aria-hidden />} onClick={() => void submit('published')}>
                Опубликовать проект
              </Button>
            </div>
          </div>
        </div>
      </form>
    </div>
  )
}

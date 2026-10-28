import { useState, type FormEvent } from 'react'
import { CalendarRange, ClipboardCheck, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { DatePicker } from '@/components/ui/DatePicker'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useDeleteContent, useDeleteTask, useMarketingMeta, useSaveContent, useSaveTask } from '@/hooks/useMarketing'
import { extractErrorMessage } from '@/lib/apiError'
import type { ContentInput, ContentItem, MarketingMeta, MarketingTask, TaskInput } from '@/types/marketing'

import { Field, FormError, hhmm } from './shared'

/** На телефоне поля выше и с 16px шрифтом — iOS не увеличивает страницу при вводе. */
const CONTROL = 'max-sm:h-11 max-sm:text-base'

function teamOptions(meta: MarketingMeta | undefined) {
  return (meta?.team ?? []).map((m) => ({ value: String(m.id), label: m.id === meta?.me ? `${m.full_name} (я)` : m.full_name }))
}

function DialogActions({ onCancel, isLoading, canDelete, onDelete }: { onCancel: () => void; isLoading: boolean; canDelete: boolean; onDelete: () => void }) {
  return (
    <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:items-center">
      {canDelete ? (
        <Button type="button" variant="ghost" className="text-danger hover:bg-danger-soft max-sm:h-11 sm:mr-auto" leftIcon={<Trash2 className="size-4" aria-hidden />} onClick={onDelete}>
          Удалить
        </Button>
      ) : <span className="hidden sm:block sm:flex-1" />}
      <Button type="button" variant="ghost" className="max-sm:h-11" onClick={onCancel}>Отмена</Button>
      <Button type="submit" className="max-sm:h-11" isLoading={isLoading}>Сохранить</Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Публикация контент-плана
// ---------------------------------------------------------------------------

export interface ContentDraft {
  item?: ContentItem
  /** Дата для новой публикации (клик по дню в календаре). */
  date?: string
}

function contentForm(draft: ContentDraft, me: number | undefined): ContentInput {
  const item = draft.item
  return {
    title: item?.title ?? '',
    channel: item?.channel ?? 'instagram',
    format: item?.format ?? 'post',
    publish_date: item ? item.publish_date : draft.date ?? null,
    publish_time: item?.publish_time ? hhmm(item.publish_time) : null,
    status: item?.status ?? (draft.date ? 'preparing' : 'idea'),
    responsible: item ? item.responsible : me ?? null,
    description: item?.description ?? '',
    post_url: item?.post_url ?? '',
  }
}

export function ContentDialog({ draft, onClose }: { draft: ContentDraft | null; onClose: () => void }) {
  return (
    <Modal isOpen={draft !== null} onClose={onClose} title={draft?.item ? 'Публикация' : 'Новая публикация'} icon={<CalendarRange className="size-5 text-brand-600" aria-hidden />} size="lg">
      {draft ? <ContentForm key={draft.item?.id ?? `new-${draft.date ?? ''}`} draft={draft} onClose={onClose} /> : null}
    </Modal>
  )
}

function ContentForm({ draft, onClose }: { draft: ContentDraft; onClose: () => void }) {
  const meta = useMarketingMeta()
  const save = useSaveContent()
  const remove = useDeleteContent()
  const { showToast } = useToast()
  const [form, setForm] = useState<ContentInput>(() => contentForm(draft, meta.data?.me))
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const set = <K extends keyof ContentInput>(key: K, value: ContentInput[K]) => setForm((f) => ({ ...f, [key]: value }))
  const needsDate = form.status === 'scheduled' || form.status === 'published'

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!form.title.trim()) return setError('Укажите тему публикации.')
    if (needsDate && !form.publish_date) return setError('Для статуса «Запланировано» и «Опубликовано» нужна дата публикации.')
    const body = { ...form, title: form.title.trim(), publish_time: form.publish_date ? form.publish_time : null }
    save.mutate({ id: draft.item?.id ?? null, body }, {
      onSuccess: () => {
        showToast(draft.item ? 'Публикация сохранена' : 'Публикация добавлена в план', 'success')
        onClose()
      },
      onError: (e) => setError(extractErrorMessage(e)),
    })
  }

  const confirmDelete = () => {
    if (!draft.item) return
    remove.mutate(draft.item.id, {
      onSuccess: () => {
        showToast('Публикация удалена', 'success')
        onClose()
      },
      onError: (e) => {
        setConfirming(false)
        setError(extractErrorMessage(e))
      },
    })
  }

  const m = meta.data
  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <FormError message={error} />
      <Field id="c-title" label="Тема" required>
        <Input id="c-title" className={CONTROL} value={form.title} maxLength={200} onChange={(e) => set('title', e.target.value)} placeholder="Например: открытый урок по робототехнике" autoFocus={!draft.item} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="c-channel" label="Канал">
          <Select id="c-channel" className={CONTROL} value={form.channel} options={m?.channels ?? []} onChange={(e) => set('channel', e.target.value as ContentInput['channel'])} />
        </Field>
        <Field id="c-format" label="Формат">
          <Select id="c-format" className={CONTROL} value={form.format} options={m?.formats ?? []} onChange={(e) => set('format', e.target.value as ContentInput['format'])} />
        </Field>
        <Field id="c-status" label="Статус">
          <Select id="c-status" className={CONTROL} value={form.status} options={m?.content_statuses ?? []} onChange={(e) => set('status', e.target.value as ContentInput['status'])} />
        </Field>
        <Field id="c-responsible" label="Ответственный">
          <Select id="c-responsible" className={CONTROL} value={form.responsible ? String(form.responsible) : ''} placeholder="Не назначен" options={teamOptions(m)} onChange={(e) => set('responsible', e.target.value ? Number(e.target.value) : null)} />
        </Field>
        <Field id="c-date" label="Дата публикации" required={needsDate}>
          <DatePicker id="c-date" className={CONTROL} value={form.publish_date ?? ''} onChange={(e) => set('publish_date', e.target.value || null)} />
        </Field>
        <Field id="c-time" label="Время">
          <Input id="c-time" type="time" className={CONTROL} value={form.publish_time ?? ''} disabled={!form.publish_date} onChange={(e) => set('publish_time', e.target.value || null)} />
        </Field>
      </div>
      {form.status === 'published' || form.post_url ? (
        <Field id="c-url" label="Ссылка на публикацию">
          <Input id="c-url" type="url" inputMode="url" className={CONTROL} value={form.post_url} maxLength={500} onChange={(e) => set('post_url', e.target.value)} placeholder="https://" />
        </Field>
      ) : null}
      <Field id="c-description" label="Описание и заметки">
        <Textarea id="c-description" rows={3} className="max-sm:text-base" value={form.description} onChange={(e) => set('description', e.target.value)} placeholder="Идея, текст, ссылки на материалы" />
      </Field>
      {draft.item?.created_by_info ? <p className="text-xs text-ink-muted">Добавил(а): {draft.item.created_by_info.full_name}</p> : null}
      <DialogActions onCancel={onClose} isLoading={save.isPending} canDelete={Boolean(draft.item?.can_delete)} onDelete={() => setConfirming(true)} />
      <ConfirmDialog
        isOpen={confirming}
        title="Удалить публикацию?"
        message="Публикация исчезнет из контент-плана и отчётов. Это действие нельзя отменить."
        confirmLabel="Удалить"
        tone="danger"
        isLoading={remove.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setConfirming(false)}
      />
    </form>
  )
}

// ---------------------------------------------------------------------------
// Задача
// ---------------------------------------------------------------------------

function taskForm(task: MarketingTask | undefined, me: number | undefined): TaskInput {
  return {
    title: task?.title ?? '',
    description: task?.description ?? '',
    due_date: task?.due_date ?? null,
    priority: task?.priority ?? 'medium',
    status: task?.status ?? 'todo',
    responsible: task ? task.responsible : me ?? null,
  }
}

/** `task === undefined` — диалог закрыт, `null` — новая задача. */
export function TaskDialog({ task, onClose }: { task: MarketingTask | null | undefined; onClose: () => void }) {
  return (
    <Modal isOpen={task !== undefined} onClose={onClose} title={task ? 'Задача' : 'Новая задача'} icon={<ClipboardCheck className="size-5 text-brand-600" aria-hidden />}>
      {task !== undefined ? <TaskForm key={task?.id ?? 'new'} task={task ?? undefined} onClose={onClose} /> : null}
    </Modal>
  )
}

function TaskForm({ task, onClose }: { task?: MarketingTask; onClose: () => void }) {
  const meta = useMarketingMeta()
  const save = useSaveTask()
  const remove = useDeleteTask()
  const { showToast } = useToast()
  const [form, setForm] = useState<TaskInput>(() => taskForm(task, meta.data?.me))
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const set = <K extends keyof TaskInput>(key: K, value: TaskInput[K]) => setForm((f) => ({ ...f, [key]: value }))

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!form.title.trim()) return setError('Укажите название задачи.')
    save.mutate({ id: task?.id ?? null, body: { ...form, title: form.title.trim() } }, {
      onSuccess: () => {
        showToast(task ? 'Задача сохранена' : 'Задача добавлена', 'success')
        onClose()
      },
      onError: (e) => setError(extractErrorMessage(e)),
    })
  }

  const confirmDelete = () => {
    if (!task) return
    remove.mutate(task.id, {
      onSuccess: () => {
        showToast('Задача удалена', 'success')
        onClose()
      },
      onError: (e) => {
        setConfirming(false)
        setError(extractErrorMessage(e))
      },
    })
  }

  const m = meta.data
  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <FormError message={error} />
      <Field id="t-title" label="Название" required>
        <Input id="t-title" className={CONTROL} value={form.title} maxLength={200} onChange={(e) => set('title', e.target.value)} placeholder="Например: снять видео с открытого урока" autoFocus={!task} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="t-due" label="Срок">
          <DatePicker id="t-due" className={CONTROL} value={form.due_date ?? ''} onChange={(e) => set('due_date', e.target.value || null)} />
        </Field>
        <Field id="t-priority" label="Приоритет">
          <Select id="t-priority" className={CONTROL} value={form.priority} options={m?.priorities ?? []} onChange={(e) => set('priority', e.target.value as TaskInput['priority'])} />
        </Field>
        <Field id="t-status" label="Статус">
          <Select id="t-status" className={CONTROL} value={form.status} options={m?.task_statuses ?? []} onChange={(e) => set('status', e.target.value as TaskInput['status'])} />
        </Field>
        <Field id="t-responsible" label="Ответственный">
          <Select id="t-responsible" className={CONTROL} value={form.responsible ? String(form.responsible) : ''} placeholder="Не назначен" options={teamOptions(m)} onChange={(e) => set('responsible', e.target.value ? Number(e.target.value) : null)} />
        </Field>
      </div>
      <Field id="t-description" label="Описание">
        <Textarea id="t-description" rows={3} className="max-sm:text-base" value={form.description} onChange={(e) => set('description', e.target.value)} />
      </Field>
      {task?.created_by_info ? <p className="text-xs text-ink-muted">Поставил(а): {task.created_by_info.full_name}</p> : null}
      <DialogActions onCancel={onClose} isLoading={save.isPending} canDelete={Boolean(task?.can_delete)} onDelete={() => setConfirming(true)} />
      <ConfirmDialog
        isOpen={confirming}
        title="Удалить задачу?"
        message="Задача исчезнет из списка и отчётов. Это действие нельзя отменить."
        confirmLabel="Удалить"
        tone="danger"
        isLoading={remove.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setConfirming(false)}
      />
    </form>
  )
}

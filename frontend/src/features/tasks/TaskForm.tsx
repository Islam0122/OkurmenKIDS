import { useState } from 'react'
import { Plus, X } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useTaskMutations, useTasksMeta } from '@/hooks/useOperations'
import { extractErrorMessage } from '@/lib/apiError'
import type { Department, Priority, RecurrenceInput, TaskDetail, TaskInput } from '@/types/operations'

function toLocalInput(value: string | null | undefined): string {
  if (!value) return ''
  const d = new Date(value)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

/** Создание и изменение задачи. Кому можно ставить задачи, решает сервер
 * (список исполнителей приходит из /tasks/meta/ уже отфильтрованным). */
export function TaskFormModal({ task, onClose, onSaved, defaults }: { task?: TaskDetail; onClose: () => void; onSaved?: (id: number) => void; defaults?: Partial<TaskInput> }) {
  const meta = useTasksMeta()
  const { create, update, saveRecurrence } = useTaskMutations()
  const { showToast } = useToast()
  const [form, setForm] = useState<TaskInput>({
    title: task?.title ?? '',
    description: task?.description ?? '',
    assignee: task ? task.assignee?.id ?? null : defaults?.assignee ?? meta.data?.me.id ?? null,
    department: task?.department ?? defaults?.department,
    reviewer: task?.reviewer?.id ?? null,
    priority: task?.priority ?? 'medium',
    category: task?.category ?? 'general',
    start_date: task?.start_date ?? null,
    deadline: task?.deadline ?? null,
    requires_approval: task?.requires_approval ?? false,
  })
  const [checklist, setChecklist] = useState<string[]>([])
  const [item, setItem] = useState('')
  const [repeat, setRepeat] = useState<'' | 'daily' | 'weekly' | 'monthly'>('')
  const [weekdays, setWeekdays] = useState<number[]>([0])
  const [monthDay, setMonthDay] = useState(1)
  const busy = create.isPending || update.isPending || saveRecurrence.isPending
  const onError = (e: unknown) => showToast(extractErrorMessage(e), 'error')

  const submit = () => {
    if (task) {
      update.mutate({ id: task.id, body: form }, { onSuccess: () => { showToast('Задача сохранена', 'success'); onClose() }, onError })
      return
    }
    if (repeat) {
      if (!form.assignee) return showToast('Для повторяющейся задачи выберите исполнителя', 'error')
      const body: RecurrenceInput = {
        title: form.title, description: form.description, assignee: form.assignee, priority: form.priority, category: form.category,
        requires_approval: form.requires_approval, checklist, frequency: repeat, weekdays: repeat === 'weekly' ? weekdays : [],
        month_day: repeat === 'monthly' ? monthDay : null, due_time: form.deadline ? new Date(form.deadline).toTimeString().slice(0, 5) : null,
        starts_on: form.start_date ?? new Date().toISOString().slice(0, 10),
      }
      saveRecurrence.mutate({ id: null, body }, { onSuccess: () => { showToast('Повторяющаяся задача создана', 'success'); onClose() }, onError })
      return
    }
    create.mutate({ ...form, checklist }, { onSuccess: (created) => { showToast('Задача создана', 'success'); onSaved?.(created.id); onClose() }, onError })
  }

  const assignees = meta.data?.assignees ?? []
  return (
    <Modal isOpen onClose={onClose} title={task ? 'Изменить задачу' : 'Новая задача'} size="lg">
      <div className="space-y-3">
        <label className="block"><span className="field-label">Название *</span><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
        <label className="block"><span className="field-label">Описание</span><Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block"><span className="field-label">Исполнитель</span>
            <Select value={form.assignee ? String(form.assignee) : ''} placeholder={meta.data?.can_assign_others ? 'Весь отдел (без исполнителя)' : undefined}
              options={assignees.map((p) => ({ value: String(p.id), label: `${p.full_name} — ${p.role_label}` }))}
              onChange={(e) => setForm({ ...form, assignee: e.target.value ? Number(e.target.value) : null })} /></label>
          {!form.assignee ? (
            <label className="block"><span className="field-label">Отдел</span>
              <Select value={form.department ?? ''} placeholder="Выберите отдел" options={meta.data?.departments ?? []} onChange={(e) => setForm({ ...form, department: e.target.value as Department })} /></label>
          ) : (
            <label className="block"><span className="field-label">Проверяющий (пусто — автор)</span>
              <Select value={form.reviewer ? String(form.reviewer) : ''} placeholder="Автор задачи" options={assignees.map((p) => ({ value: String(p.id), label: p.full_name }))} onChange={(e) => setForm({ ...form, reviewer: e.target.value ? Number(e.target.value) : null })} /></label>
          )}
          <label className="block"><span className="field-label">Приоритет</span><Select value={form.priority} options={meta.data?.priorities ?? []} onChange={(e) => setForm({ ...form, priority: e.target.value as Priority })} /></label>
          <label className="block"><span className="field-label">Категория</span><Select value={form.category} options={meta.data?.categories ?? []} onChange={(e) => setForm({ ...form, category: e.target.value })} /></label>
          <label className="block"><span className="field-label">Дата начала</span><Input type="date" value={form.start_date ?? ''} onChange={(e) => setForm({ ...form, start_date: e.target.value || null })} /></label>
          <label className="block"><span className="field-label">{repeat ? 'Срок в течение дня' : 'Дедлайн'}</span><Input type="datetime-local" value={toLocalInput(form.deadline)} onChange={(e) => setForm({ ...form, deadline: e.target.value ? new Date(e.target.value).toISOString() : null })} /></label>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.requires_approval} onChange={(e) => setForm({ ...form, requires_approval: e.target.checked })} />Требует подтверждения (исполнитель отправляет на проверку)</label>
        {!task ? (
          <>
            <div>
              <span className="field-label">Чек-лист</span>
              <ul className="mt-1 space-y-1">{checklist.map((c, i) => <li key={i} className="flex items-center justify-between rounded-lg bg-surface-muted px-3 py-1.5 text-sm">{c}<button type="button" aria-label="Убрать пункт" onClick={() => setChecklist(checklist.filter((_, j) => j !== i))}><X className="size-4" aria-hidden /></button></li>)}</ul>
              <div className="mt-1 flex gap-2"><Input value={item} placeholder="Новый пункт" onChange={(e) => setItem(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && item.trim()) { e.preventDefault(); setChecklist([...checklist, item.trim()]); setItem('') } }} />
                <Button variant="secondary" aria-label="Добавить пункт" onClick={() => { if (item.trim()) { setChecklist([...checklist, item.trim()]); setItem('') } }}><Plus className="size-4" aria-hidden /></Button></div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block"><span className="field-label">Повторение</span>
                <Select value={repeat} placeholder="Не повторять" options={meta.data?.recurrence ?? []} onChange={(e) => setRepeat(e.target.value as typeof repeat)} /></label>
              {repeat === 'monthly' ? <label className="block"><span className="field-label">Число месяца</span><Input type="number" min={1} max={31} value={monthDay} onChange={(e) => setMonthDay(Number(e.target.value))} /></label> : null}
            </div>
            {repeat === 'weekly' ? (
              <div className="flex flex-wrap gap-1.5">{WEEKDAYS.map((d, i) => (
                <button key={d} type="button" onClick={() => setWeekdays(weekdays.includes(i) ? weekdays.filter((w) => w !== i) : [...weekdays, i].sort())}
                  className={weekdays.includes(i) ? 'rounded-lg bg-brand-500 px-3 py-1.5 text-sm text-white' : 'rounded-lg border border-border px-3 py-1.5 text-sm'}>{d}</button>
              ))}</div>
            ) : null}
          </>
        ) : null}
        <div className="flex justify-end gap-2 pt-2"><Button variant="ghost" onClick={onClose}>Отмена</Button><Button onClick={submit} isLoading={busy} disabled={!form.title.trim()}>{task ? 'Сохранить' : 'Создать'}</Button></div>
      </div>
    </Modal>
  )
}

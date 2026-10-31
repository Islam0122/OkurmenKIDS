import { useRef, useState } from 'react'
import { CheckCircle2, Paperclip, Pencil, Play, RotateCcw, Send, Trash2, XCircle } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { tasksApi } from '@/api/operations'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useTask, useTaskMutations } from '@/hooks/useOperations'
import { extractErrorMessage } from '@/lib/apiError'

import { PriorityBadge, QueryView, Section, TaskStatusBadge, dateTime, saveBlob, shortDate } from '../operations/shared'
import { TaskFormModal } from './TaskForm'

function size(bytes: number) {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} МБ` : `${Math.max(1, Math.round(bytes / 1024))} КБ`
}

/** /tasks/:id — карточка задачи: workflow (взять, сдать, подтвердить,
 * вернуть с комментарием), чек-лист, комментарии, вложения, история. */
export function TaskDetailPage() {
  const { id } = useParams()
  const taskId = Number(id)
  const query = useTask(taskId)
  const m = useTaskMutations()
  const { showToast } = useToast()
  const navigate = useNavigate()
  const [comment, setComment] = useState('')
  const [reviewComment, setReviewComment] = useState('')
  const [item, setItem] = useState('')
  const [editing, setEditing] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const onError = (e: unknown) => showToast(extractErrorMessage(e), 'error')
  const act = (action: string, text?: string) => m.act.mutate({ id: taskId, action, comment: text }, { onError, onSuccess: () => setReviewComment('') })

  return (
    <div className="space-y-4">
      <button type="button" onClick={() => navigate(-1)} className="text-sm text-ink-secondary hover:text-ink">← Назад</button>
      <QueryView query={query}>
        {(task) => {
          const can = (a: string) => task.actions.includes(a as never)
          const pending = m.act.isPending
          return (
            <div className="space-y-4">
              <PageHeader title={task.title} description={`${task.department_label} · ${task.category_label}${task.occurrence_date ? ` · повторение за ${shortDate(task.occurrence_date)}` : ''}`}
                badge={<span className="flex gap-1.5"><TaskStatusBadge status={task.status} label={task.status_label} /><PriorityBadge priority={task.priority} label={task.priority_label} /></span>}
                actions={can('edit') ? <Button variant="secondary" leftIcon={<Pencil className="size-4" aria-hidden />} onClick={() => setEditing(true)}>Изменить</Button> : null} />

              <div className="grid gap-4 lg:grid-cols-3">
                <div className="space-y-4 lg:col-span-2">
                  <Section title="Описание"><p className="whitespace-pre-line text-sm">{task.description || 'Без описания'}</p></Section>

                  <Section title={`Чек-лист${task.checklist.length ? ` (${task.checklist_done}/${task.checklist_total})` : ''}`}>
                    <ul className="space-y-1.5">
                      {task.checklist.map((c) => (
                        <li key={c.id}>
                          <label className="flex items-start gap-2 text-sm">
                            <input type="checkbox" className="mt-0.5" checked={c.is_done} disabled={['completed', 'cancelled'].includes(task.stored_status)}
                              onChange={(e) => m.toggleChecklist.mutate({ id: taskId, itemId: c.id, isDone: e.target.checked }, { onError })} />
                            <span className={c.is_done ? 'text-ink-muted line-through' : ''}>{c.text}</span>
                            {c.done_by ? <span className="ml-auto text-xs text-ink-muted">{c.done_by.full_name}</span> : null}
                          </label>
                        </li>
                      ))}
                      {!task.checklist.length ? <li className="text-sm text-ink-muted">Пунктов нет</li> : null}
                    </ul>
                    {can('edit') ? (
                      <div className="mt-3 flex gap-2"><Input value={item} placeholder="Новый пункт" onChange={(e) => setItem(e.target.value)} />
                        <Button variant="secondary" disabled={!item.trim()} onClick={() => m.addChecklist.mutate({ id: taskId, text: item }, { onError, onSuccess: () => setItem('') })}>Добавить</Button></div>
                    ) : null}
                  </Section>

                  <Section title={`Вложения (${task.attachments.length})`} actions={<>
                    <input ref={fileRef} type="file" className="hidden" onChange={(e) => { const file = e.target.files?.[0]; if (file) m.upload.mutate({ id: taskId, file }, { onError, onSuccess: () => showToast('Файл прикреплён', 'success') }); e.target.value = '' }} />
                    <Button size="sm" variant="secondary" isLoading={m.upload.isPending} leftIcon={<Paperclip className="size-4" aria-hidden />} onClick={() => fileRef.current?.click()}>Прикрепить</Button>
                  </>}>
                    <ul className="divide-y divide-border">
                      {task.attachments.map((a) => (
                        <li key={a.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                          <button type="button" className="min-w-0 truncate text-left text-brand-700 hover:underline" onClick={async () => { try { saveBlob(await tasksApi.download(a.download_url), a.original_name) } catch (e) { onError(e) } }}>{a.original_name}</button>
                          <span className="flex shrink-0 items-center gap-2 text-xs text-ink-muted">{size(a.size)} · {a.uploaded_by.full_name}
                            <button type="button" aria-label="Удалить вложение" onClick={() => m.deleteAttachment.mutate({ id: taskId, attachmentId: a.id }, { onError })}><Trash2 className="size-4" aria-hidden /></button></span>
                        </li>
                      ))}
                      {!task.attachments.length ? <li className="text-sm text-ink-muted">Файлов нет</li> : null}
                    </ul>
                  </Section>

                  <Section title={`Комментарии (${task.comments.length})`}>
                    <ul className="space-y-3">
                      {task.comments.map((c) => <li key={c.id} className="text-sm"><span className="font-medium">{c.author.full_name}</span> <span className="text-xs text-ink-muted">{dateTime(c.created_at)}</span><p className="whitespace-pre-line text-ink-secondary">{c.text}</p></li>)}
                    </ul>
                    <div className="mt-3 space-y-2"><Textarea rows={2} value={comment} placeholder="Написать комментарий" onChange={(e) => setComment(e.target.value)} />
                      <Button size="sm" disabled={!comment.trim()} isLoading={m.comment.isPending} onClick={() => m.comment.mutate({ id: taskId, text: comment }, { onError, onSuccess: () => setComment('') })}>Отправить</Button></div>
                  </Section>
                </div>

                <div className="space-y-4">
                  <Section title="Действия">
                    <div className="flex flex-col gap-2">
                      {can('start') ? <Button leftIcon={<Play className="size-4" aria-hidden />} isLoading={pending} onClick={() => act('start')}>Взять в работу</Button> : null}
                      {can('submit') ? <Button leftIcon={<Send className="size-4" aria-hidden />} isLoading={pending} onClick={() => act('submit')}>{task.requires_approval ? 'Отправить на проверку' : 'Отметить выполненной'}</Button> : null}
                      {can('approve') ? (
                        <>
                          <Textarea rows={2} value={reviewComment} placeholder="Комментарий (обязателен при возврате)" onChange={(e) => setReviewComment(e.target.value)} />
                          <Button leftIcon={<CheckCircle2 className="size-4" aria-hidden />} isLoading={pending} onClick={() => act('approve', reviewComment)}>Подтвердить</Button>
                          <Button variant="danger" leftIcon={<XCircle className="size-4" aria-hidden />} disabled={!reviewComment.trim()} onClick={() => act('reject', reviewComment)}>Вернуть на доработку</Button>
                        </>
                      ) : null}
                      {can('reopen') ? <Button variant="secondary" leftIcon={<RotateCcw className="size-4" aria-hidden />} onClick={() => act('reopen')}>Открыть снова</Button> : null}
                      {can('cancel') ? <Button variant="ghost" onClick={() => act('cancel')}>Отменить задачу</Button> : null}
                      {!task.actions.filter((a) => a !== 'edit').length ? <p className="text-sm text-ink-muted">Нет доступных действий</p> : null}
                    </div>
                  </Section>
                  <Section title="Детали">
                    <dl className="space-y-2 text-sm">
                      <div><dt className="field-label">Исполнитель</dt><dd>{task.assignee?.full_name ?? `Отдел: ${task.department_label}`}</dd></div>
                      <div><dt className="field-label">Автор</dt><dd>{task.created_by.full_name}</dd></div>
                      <div><dt className="field-label">Проверяющий</dt><dd>{task.requires_approval ? task.reviewer?.full_name : 'Подтверждение не требуется'}</dd></div>
                      <div><dt className="field-label">Начало</dt><dd>{shortDate(task.start_date)}</dd></div>
                      <div><dt className="field-label">Дедлайн</dt><dd className={task.status === 'overdue' ? 'font-medium text-danger' : ''}>{dateTime(task.deadline)}</dd></div>
                      {task.completed_at ? <div><dt className="field-label">Выполнена</dt><dd>{dateTime(task.completed_at)}</dd></div> : null}
                    </dl>
                  </Section>
                  <Section title="История изменений">
                    <ol className="space-y-2 border-l border-border pl-4">
                      {task.history.map((h) => (
                        <li key={h.id} className="text-sm"><span className="font-medium">{h.action_label}</span>
                          <span className="block text-xs text-ink-muted">{dateTime(h.created_at)} · {h.actor?.full_name ?? 'Система'}</span>
                          {h.comment ? <span className="block text-ink-secondary">{h.comment}</span> : null}</li>
                      ))}
                    </ol>
                  </Section>
                </div>
              </div>
              {editing ? <TaskFormModal task={task} onClose={() => setEditing(false)} /> : null}
            </div>
          )
        }}
      </QueryView>
    </div>
  )
}

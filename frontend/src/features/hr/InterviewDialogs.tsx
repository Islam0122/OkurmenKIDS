import { useState, type FormEvent, type ReactNode } from 'react'
import { AlertTriangle, CalendarClock, CircleCheck, ExternalLink, XCircle } from 'lucide-react'
import { isAxiosError } from 'axios'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useCancelInterview, useCandidates, useRecordInterviewResult, useRecruitmentMeta, useSaveInterview } from '@/hooks/useHr'
import { extractErrorMessage } from '@/lib/apiError'
import type { Interview, InterviewConflict, InterviewFormat, InterviewResult, NextStep, RecruitmentMeta } from '@/types/hr'
import { formatDateShort } from '@/utils/format'

import { Field, FormActions, FormError, INTERVIEW_TONE, officeDate, officeDateTime, officeTime, toLocalInput } from './shared'

function conflictsOf(error: unknown): InterviewConflict[] | null {
  if (!isAxiosError(error) || error.response?.status !== 409) return null
  const data = error.response.data as { code?: string; conflicts?: InterviewConflict[] }
  return data.code === 'interview_conflict' ? data.conflicts ?? [] : null
}

/** Назначение или перенос. Если сервер видит встречу того же кандидата на
 * близкое время или занятого интервьюера — показываем предупреждение и
 * назначаем только после явного подтверждения. */
export function InterviewForm({ interview, candidateId, defaultStart, meta, onClose }: {
  interview?: Interview
  candidateId?: number
  defaultStart?: string
  meta: RecruitmentMeta
  onClose: () => void
}) {
  const { showToast } = useToast()
  const save = useSaveInterview()
  const needsCandidate = !interview && !candidateId
  const candidates = useCandidates({ active: 'true', ordering: 'last_name', page_size: 100 }, needsCandidate)
  const [form, setForm] = useState({
    candidate: candidateId ? String(candidateId) : '',
    scheduled_at: interview ? toLocalInput(interview.scheduled_at) : defaultStart ?? '',
    duration_minutes: String(interview?.duration_minutes ?? 60),
    format: interview?.format ?? ('in_person' as InterviewFormat),
    location: interview?.location ?? '',
    meeting_url: interview?.meeting_url ?? '',
    interviewer: interview ? String(interview.interviewer) : '',
    notes: interview?.notes ?? '',
  })
  const [error, setError] = useState<string | null>(null)
  const [conflicts, setConflicts] = useState<InterviewConflict[] | null>(null)
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
    setConflicts(null)
  }

  const submit = async (confirm: boolean) => {
    setError(null)
    const missing = []
    if (needsCandidate && !form.candidate) missing.push('кандидата')
    if (!form.scheduled_at) missing.push('дату и время')
    if (!form.interviewer) missing.push('интервьюера')
    if (form.format === 'online' && !form.meeting_url.trim()) missing.push('ссылку на встречу')
    if (form.format === 'in_person' && !form.location.trim()) missing.push('место проведения')
    if (missing.length) {
      setError(`Укажите ${missing.join(', ')}.`)
      return
    }
    const payload = {
      scheduled_at: form.scheduled_at, duration_minutes: Number(form.duration_minutes), format: form.format,
      location: form.location.trim(), meeting_url: form.meeting_url.trim(), interviewer: Number(form.interviewer),
      notes: form.notes, confirm,
    }
    try {
      await save.mutateAsync({ id: interview?.id, candidate: Number(form.candidate) || candidateId, payload })
      showToast(interview ? 'Собеседование сохранено' : 'Собеседование назначено', 'success')
      onClose()
    } catch (err) {
      const found = conflictsOf(err)
      if (found) setConflicts(found)
      else setError(extractErrorMessage(err))
    }
  }

  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); void submit(false) }} className="space-y-3" noValidate>
      {needsCandidate ? (
        <Field id="int-candidate" label="Кандидат" required>
          <Select id="int-candidate" value={form.candidate} onChange={set('candidate')} placeholder={candidates.isPending ? 'Загрузка…' : 'Выберите кандидата'}
            options={(candidates.data?.results ?? []).map((c) => ({ value: String(c.id), label: `${c.full_name} · ${c.position_label || 'без должности'}` }))} />
        </Field>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="int-when" label="Дата и время" required><Input id="int-when" type="datetime-local" value={form.scheduled_at} onChange={set('scheduled_at')} /></Field>
        <Field id="int-duration" label="Длительность, мин" required><Input id="int-duration" type="number" min={15} max={480} step={15} value={form.duration_minutes} onChange={set('duration_minutes')} /></Field>
        <Field id="int-format" label="Формат" required><Select id="int-format" value={form.format} onChange={set('format')} options={meta.interview_formats} /></Field>
        <Field id="int-interviewer" label="Интервьюер" required>
          <Select id="int-interviewer" value={form.interviewer} onChange={set('interviewer')} placeholder="Выберите интервьюера" options={meta.people.map((p) => ({ value: String(p.id), label: `${p.full_name} · ${p.role_label}` }))} />
        </Field>
      </div>
      {form.format === 'online' ? (
        <Field id="int-url" label="Ссылка на онлайн-встречу" required><Input id="int-url" type="url" placeholder="https://" value={form.meeting_url} onChange={set('meeting_url')} /></Field>
      ) : (
        <Field id="int-location" label="Место проведения" required={form.format === 'in_person'}><Input id="int-location" value={form.location} onChange={set('location')} maxLength={255} /></Field>
      )}
      <Field id="int-notes" label="Заметки"><Textarea id="int-notes" rows={3} value={form.notes} onChange={set('notes')} /></Field>
      {conflicts ? (
        <div className="space-y-2 rounded-xl bg-warning-soft px-3 py-2 text-sm text-warning" role="alert">
          <p className="flex items-center gap-2 font-medium"><AlertTriangle className="size-4" aria-hidden />Возможное дублирование встречи</p>
          <ul className="list-disc pl-5">
            {conflicts.map((c) => <li key={`${c.type}-${c.interview_id}`}>{c.message} ({officeDateTime(c.scheduled_at)})</li>)}
          </ul>
          <Button type="button" size="sm" variant="secondary" isLoading={save.isPending} onClick={() => void submit(true)}>Всё равно назначить</Button>
        </div>
      ) : null}
      <FormError message={error} />
      <FormActions onCancel={onClose} isLoading={save.isPending} submitLabel={interview ? 'Сохранить' : 'Назначить'} />
    </form>
  )
}

function CancelForm({ interview, onClose }: { interview: Interview; onClose: () => void }) {
  const { showToast } = useToast()
  const cancel = useCancelInterview()
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!reason.trim()) {
      setError('Укажите причину отмены.')
      return
    }
    try {
      await cancel.mutateAsync({ id: interview.id, reason: reason.trim() })
      showToast('Собеседование отменено', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <Field id="int-cancel" label="Причина отмены" required><Input id="int-cancel" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={255} /></Field>
      <FormError message={error} />
      <FormActions onCancel={onClose} isLoading={cancel.isPending} submitLabel="Отменить собеседование" />
    </form>
  )
}

function ResultForm({ interview, meta, onClose }: { interview: Interview; meta: RecruitmentMeta; onClose: () => void }) {
  const { showToast } = useToast()
  const record = useRecordInterviewResult()
  const [form, setForm] = useState({ result: '' as InterviewResult | '', next_step: '' as NextStep | '', result_comment: '', next_step_date: '' })
  const [error, setError] = useState<string | null>(null)
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!form.result || !form.next_step) {
      setError('Укажите результат и следующий шаг.')
      return
    }
    try {
      await record.mutateAsync({
        id: interview.id,
        payload: { result: form.result, next_step: form.next_step, result_comment: form.result_comment, next_step_date: form.next_step_date || null },
      })
      showToast('Результат зафиксирован', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="int-result" label="Результат" required><Select id="int-result" value={form.result} onChange={set('result')} placeholder="Выберите" options={meta.interview_results} /></Field>
        <Field id="int-next" label="Следующий шаг" required><Select id="int-next" value={form.next_step} onChange={set('next_step')} placeholder="Выберите" options={meta.next_steps} /></Field>
        <Field id="int-next-date" label="Дата следующего этапа"><DatePicker id="int-next-date" value={form.next_step_date} onChange={set('next_step_date')} /></Field>
      </div>
      <Field id="int-comment" label="Комментарий"><Textarea id="int-comment" rows={3} value={form.result_comment} onChange={set('result_comment')} /></Field>
      <p className="text-xs text-ink-muted">Этап кандидата изменится по следующему шагу: предложение, ожидание решения, отказ или следующее собеседование.</p>
      <FormError message={error} />
      <FormActions onCancel={onClose} isLoading={record.isPending} submitLabel="Зафиксировать" />
    </form>
  )
}

/** Карточка собеседования с действиями: перенос/изменение, отмена, результат. */
export function InterviewModal({ interview, onClose }: { interview: Interview | null; onClose: () => void }) {
  const meta = useRecruitmentMeta()
  const [mode, setMode] = useState<'view' | 'edit' | 'cancel' | 'result'>('view')
  const close = () => {
    setMode('view')
    onClose()
  }
  const titles = { view: 'Собеседование', edit: 'Перенести или изменить', cancel: 'Отменить собеседование', result: 'Результат собеседования' }
  return (
    <Modal isOpen={interview !== null} onClose={close} title={titles[mode]} icon={<CalendarClock className="size-5 text-brand-600" aria-hidden />}>
      {interview && meta.data ? (
        mode === 'edit' ? <InterviewForm interview={interview} meta={meta.data} onClose={close} />
          : mode === 'cancel' ? <CancelForm interview={interview} onClose={close} />
            : mode === 'result' ? <ResultForm interview={interview} meta={meta.data} onClose={close} />
              : <InterviewDetails interview={interview} onAction={setMode} />
      ) : null}
    </Modal>
  )
}

function InterviewDetails({ interview: i, onAction }: { interview: Interview; onAction: (mode: 'edit' | 'cancel' | 'result') => void }) {
  const rows: [string, ReactNode][] = [
    ['Кандидат', <Link key="c" className="text-brand-700 hover:underline" to={`/hr/candidates/${i.candidate}`}>{i.candidate_info.full_name}</Link>],
    ['Должность / вакансия', i.vacancy_info?.title || '—'],
    ['Дата и время', `${formatDateShort(officeDate(i.scheduled_at))}, ${officeTime(i.scheduled_at)} · ${i.duration_minutes} мин`],
    ['Формат', i.format_label],
    ['Интервьюер', `${i.interviewer_info.full_name} · ${i.interviewer_info.role_label}`],
  ]
  if (i.location) rows.push(['Место', i.location])
  if (i.meeting_url) {
    rows.push(['Ссылка', <a key="u" className="inline-flex items-center gap-1 break-all text-brand-700 hover:underline" href={i.meeting_url} target="_blank" rel="noreferrer">{i.meeting_url}<ExternalLink className="size-3.5" aria-hidden /></a>])
  }
  if (i.notes) rows.push(['Заметки', i.notes])
  if (i.reschedule_count) rows.push(['Переносов', String(i.reschedule_count)])
  if (i.status === 'cancelled') rows.push(['Причина отмены', i.cancel_reason])
  if (i.status === 'completed') {
    rows.push(['Результат', i.result_label])
    rows.push(['Следующий шаг', i.next_step_label + (i.next_step_date ? ` · ${formatDateShort(i.next_step_date)}` : '')])
    if (i.result_comment) rows.push(['Комментарий', i.result_comment])
  }
  return (
    <div className="space-y-4">
      <Badge tone={INTERVIEW_TONE[i.status]}>{i.status_label}</Badge>
      <dl className="space-y-2">
        {rows.map(([label, value]) => (
          <div key={label} className="grid gap-1 sm:grid-cols-[10rem_1fr]">
            <dt className="text-xs uppercase tracking-wide text-ink-muted">{label}</dt>
            <dd className="whitespace-pre-line break-words text-sm text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      {i.status === 'scheduled' ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" leftIcon={<CircleCheck className="size-4" aria-hidden />} onClick={() => onAction('result')}>Зафиксировать результат</Button>
          <Button size="sm" variant="secondary" leftIcon={<CalendarClock className="size-4" aria-hidden />} onClick={() => onAction('edit')}>Перенести / изменить</Button>
          <Button size="sm" variant="ghost" leftIcon={<XCircle className="size-4" aria-hidden />} onClick={() => onAction('cancel')}>Отменить</Button>
        </div>
      ) : null}
    </div>
  )
}

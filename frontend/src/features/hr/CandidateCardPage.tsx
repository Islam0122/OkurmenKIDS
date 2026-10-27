import { useState, type FormEvent, type ReactNode } from 'react'
import { ArrowRightLeft, CalendarPlus, PencilLine, UserCheck } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import {
  useAddCandidateNote,
  useAllVacancies,
  useCandidate,
  useCandidateHistory,
  useChangeCandidateStatus,
  useHireCandidate,
  useInterviews,
  useRecruitmentMeta,
} from '@/hooks/useHr'
import { useHrMeta } from '@/hooks/useHrEmployees'
import { extractErrorMessage } from '@/lib/apiError'
import type { Candidate, CandidateStatus, HRRoleOption, Interview } from '@/types/hr'
import { formatDateShort } from '@/utils/format'

import { CandidateForm } from './CandidatesPage'
import { InterviewForm, InterviewModal } from './InterviewDialogs'
import { ActivityList, CandidateStatusBadge, Field, FormActions, FormError, INTERVIEW_TONE, officeDateTime } from './shared'

type Dialog = 'edit' | 'status' | 'interview' | 'hire' | null

const SCHEDULABLE: CandidateStatus[] = ['new', 'contacted', 'interview_scheduled', 'interview_done', 'awaiting_decision']

/** /hr/candidates/:id — карточка кандидата. */
export function HrCandidateCardPage() {
  const id = Number(useParams().id)
  const candidate = useCandidate(id)
  const meta = useRecruitmentMeta()
  const vacancies = useAllVacancies()
  const interviews = useInterviews({ candidate: id })
  const history = useCandidateHistory(id)
  const [dialog, setDialog] = useState<Dialog>(null)
  const [opened, setOpened] = useState<Interview | null>(null)

  if (candidate.isPending || meta.isPending) return <LoadingState label="Загружаем карточку кандидата…" />
  if (candidate.isError) return <ErrorState title="Карточка недоступна" message={extractErrorMessage(candidate.error)} onRetry={() => void candidate.refetch()} />
  if (meta.isError) return <ErrorState message={extractErrorMessage(meta.error)} onRetry={() => void meta.refetch()} />
  const c = candidate.data
  // Те же этапы, с которых сервер позволяет назначить встречу (pipeline.SCHEDULABLE).
  const canSchedule = SCHEDULABLE.includes(c.status)
  const openedFresh = opened ? (interviews.data ?? []).find((i) => i.id === opened.id) ?? opened : null

  const details: [string, ReactNode][] = [
    ['Телефон', c.phone || '—'],
    ['Email', c.email || '—'],
    ['Вакансия / должность', c.position_label || '—'],
    ['Источник', c.source_label + (c.source_details ? ` · ${c.source_details}` : '')],
    ['Дата добавления', formatDateShort(c.added_on)],
    ['Ответственный', c.responsible_info?.full_name ?? '—'],
    ['Этап изменён', officeDateTime(c.status_changed_at)],
  ]

  return (
    <div className="space-y-5">
      <BackLink to="/hr/candidates">Кандидаты</BackLink>
      <Card>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-ink sm:text-2xl">{c.full_name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <CandidateStatusBadge status={c.status} label={c.status_label} />
              {c.hired_user_info ? (
                <Link to={`/hr/employees/${c.hired_user_info.id}`} className="text-sm text-brand-700 hover:underline">
                  Учётная запись: {c.hired_user_info.username}
                </Link>
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {c.status === 'offer' ? (
              <Button size="sm" leftIcon={<UserCheck className="size-4" aria-hidden />} onClick={() => setDialog('hire')}>Принять на работу</Button>
            ) : null}
            {canSchedule ? (
              <Button size="sm" variant="secondary" leftIcon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => setDialog('interview')}>Назначить собеседование</Button>
            ) : null}
            {c.allowed_statuses.length ? (
              <Button size="sm" variant="secondary" leftIcon={<ArrowRightLeft className="size-4" aria-hidden />} onClick={() => setDialog('status')}>Сменить этап</Button>
            ) : null}
            <Button size="sm" variant="ghost" leftIcon={<PencilLine className="size-4" aria-hidden />} onClick={() => setDialog('edit')}>Изменить</Button>
          </div>
        </div>
        <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {details.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs uppercase tracking-wide text-ink-muted">{label}</dt>
              <dd className="break-words text-sm text-ink">{value}</dd>
            </div>
          ))}
        </dl>
        {c.notes ? (
          <div className="mt-4">
            <p className="text-xs uppercase tracking-wide text-ink-muted">Заметки</p>
            <p className="whitespace-pre-line break-words text-sm text-ink">{c.notes}</p>
          </div>
        ) : null}
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Собеседования">
          {interviews.isPending ? <LoadingState /> : interviews.isError ? (
            <ErrorState message={extractErrorMessage(interviews.error)} onRetry={() => void interviews.refetch()} />
          ) : interviews.data.length === 0 ? (
            <p className="text-sm text-ink-secondary">Собеседований ещё не было.</p>
          ) : (
            <ul className="divide-y divide-border">
              {interviews.data.map((item) => (
                <li key={item.id}>
                  <button type="button" onClick={() => setOpened(item)} className="flex w-full flex-wrap items-center justify-between gap-2 py-2.5 text-left hover:bg-surface-hover">
                    <span className="min-w-0">
                      <span className="block text-sm font-medium tabular-nums text-ink">{officeDateTime(item.scheduled_at)}</span>
                      <span className="block text-xs text-ink-secondary">{item.format_label} · {item.interviewer_info.full_name}{item.result_label ? ` · ${item.result_label}` : ''}</span>
                    </span>
                    <Badge tone={INTERVIEW_TONE[item.status]}>{item.status_label}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="История взаимодействия">
          <NoteForm candidateId={c.id} />
          <div className="mt-4">
            {history.isPending ? <LoadingState /> : history.isError ? (
              <ErrorState message={extractErrorMessage(history.error)} onRetry={() => void history.refetch()} />
            ) : <ActivityList items={history.data} showSubject={false} />}
          </div>
        </Card>
      </div>

      <Modal isOpen={dialog === 'edit'} onClose={() => setDialog(null)} title="Изменить кандидата">
        {dialog === 'edit' ? <CandidateForm candidate={c} meta={meta.data} vacancies={vacancies.data?.results ?? []} onClose={() => setDialog(null)} /> : null}
      </Modal>
      <Modal isOpen={dialog === 'status'} onClose={() => setDialog(null)} title="Сменить этап">
        {dialog === 'status' ? <StatusForm candidate={c} onClose={() => setDialog(null)} /> : null}
      </Modal>
      <Modal isOpen={dialog === 'interview'} onClose={() => setDialog(null)} title="Назначить собеседование">
        {dialog === 'interview' ? <InterviewForm candidateId={c.id} meta={meta.data} onClose={() => setDialog(null)} /> : null}
      </Modal>
      <Modal isOpen={dialog === 'hire'} onClose={() => setDialog(null)} title="Принять на работу">
        {dialog === 'hire' ? <HireForm candidate={c} onClose={() => setDialog(null)} /> : null}
      </Modal>
      <InterviewModal interview={openedFresh} onClose={() => setOpened(null)} />
    </div>
  )
}

function StatusForm({ candidate, onClose }: { candidate: Candidate; onClose: () => void }) {
  const { showToast } = useToast()
  const change = useChangeCandidateStatus()
  const [status, setStatus] = useState<CandidateStatus | ''>('')
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!status) {
      setError('Выберите этап.')
      return
    }
    try {
      await change.mutateAsync({ id: candidate.id, status, comment: comment.trim() })
      showToast('Этап изменён', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <p className="text-sm text-ink-secondary">
        Сейчас: <strong>{candidate.status_label}</strong>. Доступны только допустимые переходы; этапы собеседований
        ставятся самими собеседованиями, «Принят на работу» — кнопкой найма.
      </p>
      <Field id="cand-status" label="Новый этап" required>
        <Select id="cand-status" value={status} onChange={(e) => setStatus(e.target.value as CandidateStatus)} placeholder="Выберите этап" options={candidate.allowed_statuses} />
      </Field>
      <Field id="cand-status-comment" label="Комментарий"><Textarea id="cand-status-comment" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={1000} /></Field>
      {status === 'rejected' || status === 'withdrawn' || status === 'offer' ? (
        <p className="text-xs text-warning">Назначенные собеседования кандидата будут отменены.</p>
      ) : null}
      <FormError message={error} />
      <FormActions onCancel={onClose} isLoading={change.isPending} submitLabel="Сменить этап" />
    </form>
  )
}

function NoteForm({ candidateId }: { candidateId: number }) {
  const { showToast } = useToast()
  const add = useAddCandidateNote()
  const [text, setText] = useState('')
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!text.trim()) return
    try {
      await add.mutateAsync({ id: candidateId, text: text.trim() })
      setText('')
      showToast('Запись добавлена', 'success')
    } catch (err) {
      showToast(extractErrorMessage(err), 'error')
    }
  }
  return (
    <form onSubmit={submit} className="space-y-2">
      <label htmlFor="cand-note" className="sr-only">Новая запись</label>
      <Textarea id="cand-note" rows={2} placeholder="Звонок, письмо, договорённость…" value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} />
      <div className="flex justify-end">
        <Button type="submit" size="sm" isLoading={add.isPending} disabled={!text.trim()}>Добавить запись</Button>
      </div>
    </form>
  )
}

function HireForm({ candidate, onClose }: { candidate: Candidate; onClose: () => void }) {
  const { showToast } = useToast()
  const hire = useHireCandidate()
  const roles = useHrMeta().data?.roles ?? []
  const [form, setForm] = useState({
    username: '', email: candidate.email, first_name: candidate.first_name, last_name: candidate.last_name,
    role: '' as HRRoleOption['value'] | '', password: '', password_confirm: '',
  })
  const [error, setError] = useState<string | null>(null)
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!form.username.trim() || !form.email.trim() || !form.first_name.trim() || !form.role || !form.password) {
      setError('Заполните логин, email, имя, должность и пароль.')
      return
    }
    if (form.password !== form.password_confirm) {
      setError('Пароли не совпадают.')
      return
    }
    try {
      await hire.mutateAsync({
        id: candidate.id,
        payload: { ...form, username: form.username.trim(), email: form.email.trim(), first_name: form.first_name.trim(), last_name: form.last_name.trim(), role: form.role },
      })
      showToast('Кандидат принят: учётная запись создана', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <p className="text-sm text-ink-secondary">Будет создана учётная запись сотрудника, связанная с кандидатом. Повторно принять того же кандидата нельзя.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="hire-first" label="Имя" required><Input id="hire-first" value={form.first_name} onChange={set('first_name')} maxLength={100} /></Field>
        <Field id="hire-last" label="Фамилия"><Input id="hire-last" value={form.last_name} onChange={set('last_name')} maxLength={100} /></Field>
        <Field id="hire-username" label="Логин" required><Input id="hire-username" value={form.username} onChange={set('username')} autoComplete="off" maxLength={150} /></Field>
        <Field id="hire-email" label="Email" required><Input id="hire-email" type="email" value={form.email} onChange={set('email')} /></Field>
      </div>
      <Field id="hire-role" label="Должность" required>
        <Select id="hire-role" value={form.role} onChange={set('role')} placeholder="Выберите должность" options={roles.map((r) => ({ value: r.value, label: r.label }))} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="hire-password" label="Пароль" required><Input id="hire-password" type="password" value={form.password} onChange={set('password')} autoComplete="new-password" /></Field>
        <Field id="hire-password2" label="Повторите пароль" required><Input id="hire-password2" type="password" value={form.password_confirm} onChange={set('password_confirm')} autoComplete="new-password" /></Field>
      </div>
      <FormError message={error} />
      <FormActions onCancel={onClose} isLoading={hire.isPending} submitLabel="Принять на работу" />
    </form>
  )
}

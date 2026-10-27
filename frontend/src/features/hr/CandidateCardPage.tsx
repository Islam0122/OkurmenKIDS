import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import {
  AlertTriangle, ArrowRightLeft, CalendarPlus, Download, Eye, FilePlus2, PencilLine, Trash2, Upload, UserCheck,
} from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Menu } from '@/components/ui/Menu'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { recruitmentApi } from '@/api/hr'
import {
  useAddNote, useAllVacancies, useCandidate, useCandidateHistory, useCandidateNotes, useChangeApplicationStatus,
  useEraseCandidate, useHireCandidate, useInterviews, useMergeCandidate, useNotDuplicate, useRecruitmentMeta,
  useRequestAccount, useUpdateApplication, useUpdateCandidate, useUploadResume,
} from '@/hooks/useHr'
import { extractErrorMessage } from '@/lib/apiError'
import type { Application, ApplicationStatus, Candidate, Interview, PersonFields, RecruitmentMeta } from '@/types/hr'
import { cn } from '@/utils/cn'
import { formatDateShort } from '@/utils/format'

import { ApplicationForm } from './CandidatesPage'
import { InterviewForm, InterviewModal } from './InterviewDialogs'
import {
  ActivityList, ApplicationStatusBadge, Field, FormActions, FormError, INTERVIEW_TONE, candidatePath, fileSize,
  officeDateTime,
} from './shared'

type Dialog = 'profile' | 'status' | 'interview' | 'hire' | 'new_application' | 'erase' | null

const SCHEDULABLE: ApplicationStatus[] = ['new', 'screening', 'shortlisted', 'interview_scheduled', 'interview_done', 'awaiting_decision', 'next_stage']

const SUBMITTED_LABELS: Record<string, string> = {
  full_name: 'ФИО', phone: 'Телефон', email: 'Email', city: 'Город', experience: 'Опыт работы', education: 'Образование',
  skills: 'Навыки', portfolio_url: 'Портфолио',
}

function Details({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {rows.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-xs uppercase tracking-wide text-ink-muted">{label}</dt>
          <dd className="whitespace-pre-line break-words text-sm text-ink">{value || '—'}</dd>
        </div>
      ))}
    </dl>
  )
}

/** /hr/candidates/:id — карточка кандидата (человека) со всеми его откликами;
 * ?application=ID — выбранный отклик. */
export function HrCandidateCardPage() {
  const id = Number(useParams().id)
  const [params, setParams] = useSearchParams()
  const candidate = useCandidate(id)
  const meta = useRecruitmentMeta()
  const [dialog, setDialog] = useState<Dialog>(null)

  if (candidate.isPending || meta.isPending) return <LoadingState label="Загружаем карточку кандидата…" />
  if (candidate.isError) return <ErrorState title="Карточка недоступна" message={extractErrorMessage(candidate.error)} onRetry={() => void candidate.refetch()} />
  if (meta.isError) return <ErrorState message={extractErrorMessage(meta.error)} onRetry={() => void meta.refetch()} />
  const c = candidate.data
  const selectedId = Number(params.get('application')) || c.applications[0]?.id
  const application = c.applications.find((a) => a.id === selectedId) ?? c.applications[0]
  const closed = Boolean(c.erased_at || c.merged_into)
  const select = (appId: number) => {
    const next = new URLSearchParams(params)
    next.set('application', String(appId))
    setParams(next, { replace: true })
  }

  return (
    <div className="space-y-5">
      <BackLink to="/hr/candidates">Кандидаты</BackLink>
      <Card>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-ink sm:text-2xl">{c.full_name}</h1>
            <p className="mt-1 text-sm text-ink-secondary">{[c.phone, c.email, c.city].filter(Boolean).join(' · ') || 'Контакты не указаны'}</p>
          </div>
          {closed ? null : (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="secondary" leftIcon={<FilePlus2 className="size-4" aria-hidden />} onClick={() => setDialog('new_application')}>Новый отклик</Button>
              <Button size="sm" variant="ghost" leftIcon={<PencilLine className="size-4" aria-hidden />} onClick={() => setDialog('profile')}>Профиль</Button>
              <Menu items={[{ key: 'erase', label: 'Удалить персональные данные', tone: 'danger', icon: <Trash2 className="size-4" aria-hidden />, onClick: () => setDialog('erase') }]} />
            </div>
          )}
        </div>
        {c.merged_into_info ? (
          <p className="mt-4 rounded-xl bg-info-soft px-3 py-2 text-sm text-info">
            Запись объединена с <Link className="font-medium underline" to={candidatePath(c.merged_into_info.id)}>{c.merged_into_info.full_name}</Link>: отклики и история перенесены туда.
          </p>
        ) : null}
        {c.erased_at ? (
          <p className="mt-4 rounded-xl bg-surface-hover px-3 py-2 text-sm text-ink-secondary">
            Персональные данные удалены {officeDateTime(c.erased_at)}. Отклики остаются только для статистики.
          </p>
        ) : null}
        {!closed ? (
          <div className="mt-5">
            <Details rows={[['Опыт работы', c.experience], ['Образование', c.education], ['Навыки', c.skills],
              ['Портфолио', c.portfolio_url ? <a key="p" href={c.portfolio_url} target="_blank" rel="noreferrer noopener" className="text-brand-700 hover:underline">{c.portfolio_url}</a> : '']]} />
          </div>
        ) : null}
      </Card>

      {!closed ? <Duplicates candidate={c} /> : null}

      {c.applications.length === 0 ? (
        <Card><p className="text-sm text-ink-secondary">Откликов нет.</p></Card>
      ) : (
        <>
          {c.applications.length > 1 ? (
            <div className="scroll-x flex gap-2" role="tablist" aria-label="Отклики кандидата">
              {c.applications.map((a) => (
                <button key={a.id} type="button" role="tab" aria-selected={a.id === application.id} onClick={() => select(a.id)}
                  className={cn('shrink-0 rounded-xl border px-3 py-2 text-left text-sm', a.id === application.id ? 'border-brand-500 bg-brand-50' : 'border-border bg-surface hover:bg-surface-hover')}>
                  <span className="block font-medium text-ink">{a.position_label || 'Без должности'}</span>
                  <span className="block text-xs text-ink-secondary">{a.number} · {a.status_label}</span>
                </button>
              ))}
            </div>
          ) : null}
          <ApplicationPanel key={application.id} application={application} meta={meta.data} readOnly={closed} onDialog={setDialog} />
        </>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Заметки HR" description="Видны только HR — не кандидату и не на сайте">
          {closed ? null : <NoteForm candidateId={c.id} applicationId={application?.id ?? null} />}
          <NotesList candidateId={c.id} />
        </Card>
        <Card title="История действий">
          <HistoryList candidateId={c.id} />
        </Card>
      </div>

      <Modal isOpen={dialog === 'profile'} onClose={() => setDialog(null)} title="Профиль кандидата" size="lg">
        {dialog === 'profile' ? <ProfileForm candidate={c} onClose={() => setDialog(null)} /> : null}
      </Modal>
      <Modal isOpen={dialog === 'new_application'} onClose={() => setDialog(null)} title="Новый отклик кандидата" size="lg">
        {dialog === 'new_application' ? <NewApplication candidate={c} meta={meta.data} onClose={() => setDialog(null)} onSaved={select} /> : null}
      </Modal>
      {application ? (
        <>
          <Modal isOpen={dialog === 'status'} onClose={() => setDialog(null)} title="Сменить этап">
            {dialog === 'status' ? <StatusForm application={application} onClose={() => setDialog(null)} /> : null}
          </Modal>
          <Modal isOpen={dialog === 'interview'} onClose={() => setDialog(null)} title="Назначить собеседование">
            {dialog === 'interview' ? <InterviewForm applicationId={application.id} meta={meta.data} onClose={() => setDialog(null)} /> : null}
          </Modal>
          <Modal isOpen={dialog === 'hire'} onClose={() => setDialog(null)} title="Принять на работу" size="lg">
            {dialog === 'hire' ? <HireForm candidate={c} application={application} meta={meta.data} onClose={() => setDialog(null)} /> : null}
          </Modal>
        </>
      ) : null}
      <EraseDialog candidate={c} isOpen={dialog === 'erase'} onClose={() => setDialog(null)} />
    </div>
  )
}

function ApplicationPanel({ application: a, meta, readOnly, onDialog }: {
  application: Application
  meta: RecruitmentMeta
  readOnly: boolean
  onDialog: (dialog: Dialog) => void
}) {
  const interviews = useInterviews({ application: a.id })
  const update = useUpdateApplication()
  const { showToast } = useToast()
  const [opened, setOpened] = useState<Interview | null>(null)
  const openedFresh = opened ? (interviews.data ?? []).find((i) => i.id === opened.id) ?? opened : null
  const canSchedule = !readOnly && SCHEDULABLE.includes(a.status)
  const submitted = Object.entries(a.submitted_data ?? {}).filter(([, value]) => value)

  const setResponsible = async (value: string) => {
    try {
      await update.mutateAsync({ id: a.id, payload: { responsible: value ? Number(value) : null } })
      showToast('Ответственный назначен', 'success')
    } catch (err) {
      showToast(extractErrorMessage(err), 'error')
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wide text-ink-muted">Отклик {a.number}</p>
            <h2 className="text-lg font-semibold text-ink">
              {a.vacancy_info ? <Link to={`/hr/vacancies/${a.vacancy_info.id}`} className="hover:text-brand-700">{a.vacancy_info.title}</Link> : a.position || 'Без должности'}
            </h2>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <ApplicationStatusBadge status={a.status} label={a.status_label} />
              {a.vacancy_info && a.vacancy_info.status !== 'published' ? <Badge tone="muted">Вакансия: {a.vacancy_info.status_label.toLowerCase()}</Badge> : null}
              {a.hired_user_info ? (
                <Link to={`/hr/employees/${a.hired_user_info.id}`} className="text-sm text-brand-700 hover:underline">
                  Сотрудник: {a.hired_user_info.username} ({a.hired_user_info.role_label})
                </Link>
              ) : null}
            </div>
          </div>
          {readOnly ? null : (
            <div className="flex flex-wrap gap-2">
              {a.status === 'offer' && !a.pending_account_request ? (
                <Button size="sm" leftIcon={<UserCheck className="size-4" aria-hidden />} onClick={() => onDialog('hire')}>Принять на работу</Button>
              ) : null}
              {canSchedule ? (
                <Button size="sm" variant="secondary" leftIcon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => onDialog('interview')}>Назначить собеседование</Button>
              ) : null}
              {a.allowed_statuses.length ? (
                <Button size="sm" variant="secondary" leftIcon={<ArrowRightLeft className="size-4" aria-hidden />} onClick={() => onDialog('status')}>Сменить этап</Button>
              ) : null}
            </div>
          )}
        </div>
        {a.pending_account_request ? (
          <p className="mt-4 rounded-xl bg-warning-soft px-3 py-2 text-sm text-warning">
            Запрос на учётную запись «{a.pending_account_request.username}» ({a.pending_account_request.role_label}) ждёт администратора.
            Этап сменится на «Принят на работу», когда администратор создаст учётную запись.
          </p>
        ) : null}
        <div className="mt-5">
          <Details rows={[
            ['Дата отклика', formatDateShort(a.applied_on)],
            ['Канал', a.channel_label],
            ['Источник', a.source_label + (a.source_details ? ` · ${a.source_details}` : '')],
            ['Этап изменён', officeDateTime(a.status_changed_at)],
            ['Ближайшая встреча', a.next_interview_at ? officeDateTime(a.next_interview_at) : ''],
            ['Согласие на обработку данных', a.consent_at ? `${officeDateTime(a.consent_at)} (версия ${a.consent_version})` : a.channel === 'hr' ? 'Добавлен HR' : ''],
          ]} />
        </div>
        {a.cover_letter ? (
          <div className="mt-5">
            <p className="text-xs uppercase tracking-wide text-ink-muted">Сопроводительное письмо</p>
            <p className="whitespace-pre-line break-words text-sm text-ink">{a.cover_letter}</p>
          </div>
        ) : null}
        {submitted.length ? (
          <details className="mt-5 rounded-xl border border-border px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium text-ink">Анкета, как её отправил кандидат</summary>
            <dl className="mt-2 grid gap-2 sm:grid-cols-2">
              {submitted.map(([key, value]) => (
                <div key={key}><dt className="text-xs text-ink-muted">{SUBMITTED_LABELS[key] ?? key}</dt><dd className="whitespace-pre-line break-words text-sm text-ink">{value}</dd></div>
              ))}
            </dl>
          </details>
        ) : null}
      </Card>

      <div className="space-y-5">
        <Card title="Ответственный">
          <Select aria-label="Ответственный за отклик" value={a.responsible ? String(a.responsible) : ''} disabled={readOnly || update.isPending}
            onChange={(e) => void setResponsible(e.target.value)} placeholder="Не назначен"
            options={meta.people.map((p) => ({ value: String(p.id), label: `${p.full_name} · ${p.role_label}` }))} />
        </Card>
        <ResumeCard application={a} readOnly={readOnly} maxMb={meta.resume_max_mb} />
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
                      <span className="block text-xs text-ink-secondary">
                        {item.format_label} · {item.interviewer_info.full_name}
                        {item.overall_rating ? ` · ${item.overall_rating}/5` : ''}{item.result_label ? ` · ${item.result_label}` : ''}
                      </span>
                    </span>
                    <Badge tone={INTERVIEW_TONE[item.status]}>{item.status_label}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <InterviewModal interview={openedFresh} onClose={() => setOpened(null)} />
    </div>
  )
}

function ResumeCard({ application: a, readOnly, maxMb }: { application: Application; readOnly: boolean; maxMb: number }) {
  const { showToast } = useToast()
  const upload = useUploadResume()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const open = async (inline: boolean) => {
    setBusy(true)
    try {
      await recruitmentApi.openResume(a.id, inline)
    } catch (err) {
      showToast(extractErrorMessage(err, 'Не удалось открыть резюме'), 'error')
    } finally {
      setBusy(false)
    }
  }
  const replace = async (file: File | undefined) => {
    if (!file) return
    try {
      await upload.mutateAsync({ id: a.id, file })
      showToast('Резюме прикреплено', 'success')
    } catch (err) {
      showToast(extractErrorMessage(err), 'error')
    } finally {
      if (input.current) input.current.value = ''
    }
  }
  const isPdf = a.resume_name.toLowerCase().endsWith('.pdf')
  return (
    <Card title="Резюме" description="Файл доступен только HR — по защищённой ссылке">
      {a.has_resume ? (
        <div className="space-y-2">
          <p className="break-all text-sm text-ink">{a.resume_name} <span className="text-ink-muted">{fileSize(a.resume_size)}</span></p>
          <div className="flex flex-wrap gap-2">
            {isPdf ? <Button size="sm" variant="secondary" isLoading={busy} leftIcon={<Eye className="size-4" aria-hidden />} onClick={() => void open(true)}>Открыть</Button> : null}
            <Button size="sm" variant="secondary" isLoading={busy} leftIcon={<Download className="size-4" aria-hidden />} onClick={() => void open(false)}>Скачать</Button>
          </div>
        </div>
      ) : <p className="text-sm text-ink-secondary">Резюме не прикреплено.</p>}
      {readOnly ? null : (
        <>
          <input ref={input} type="file" accept=".pdf,.docx" className="sr-only" aria-label="Файл резюме" onChange={(e) => void replace(e.target.files?.[0])} />
          <Button size="sm" variant="ghost" className="mt-2" isLoading={upload.isPending} leftIcon={<Upload className="size-4" aria-hidden />} onClick={() => input.current?.click()}>
            {a.has_resume ? 'Заменить файл' : `Прикрепить (PDF/DOCX, до ${maxMb} МБ)`}
          </Button>
        </>
      )}
    </Card>
  )
}

function Duplicates({ candidate }: { candidate: Candidate }) {
  const merge = useMergeCandidate()
  const dismiss = useNotDuplicate()
  const { showToast } = useToast()
  const [target, setTarget] = useState<{ id: number; full_name: string } | null>(null)
  const flagged = candidate.applications.filter((a) => a.needs_duplicate_review)
  if (!candidate.possible_duplicates.length && !flagged.length) return null
  const doMerge = async () => {
    if (!target) return
    try {
      await merge.mutateAsync({ id: candidate.id, target: target.id })
      showToast('Записи объединены', 'success')
      window.location.assign(candidatePath(target.id))
    } catch (err) {
      showToast(extractErrorMessage(err), 'error')
      setTarget(null)
    }
  }
  return (
    <Card>
      <p className="flex items-center gap-2 text-sm font-medium text-warning"><AlertTriangle className="size-4" aria-hidden />Возможный дубль: совпадают контакты</p>
      <p className="mt-1 text-sm text-ink-secondary">Записи не объединяются автоматически. Проверьте и свяжите их, если это один человек.</p>
      <ul className="mt-3 space-y-2">
        {candidate.possible_duplicates.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border px-3 py-2">
            <span className="text-sm">
              <Link to={candidatePath(m.id)} className="font-medium text-brand-700 hover:underline">{m.full_name}</Link>
              <span className="text-ink-secondary"> · {[m.phone, m.email].filter(Boolean).join(' · ')} · совпадает {[m.same_phone ? 'телефон' : '', m.same_email ? 'email' : ''].filter(Boolean).join(' и ')} · откликов: {m.applications}</span>
            </span>
            <Button size="sm" variant="secondary" onClick={() => setTarget(m)}>Объединить с этой записью</Button>
          </li>
        ))}
      </ul>
      {flagged.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {flagged.map((a) => (
            <Button key={a.id} size="sm" variant="ghost" isLoading={dismiss.isPending} onClick={() => void dismiss.mutateAsync(a.id).then(() => showToast('Отмечено: не дубль', 'success'))}>
              Не дубль (отклик {a.number})
            </Button>
          ))}
        </div>
      ) : null}
      <ConfirmDialog
        isOpen={target !== null}
        title="Объединить записи"
        message={target ? `Отклики, заметки и история «${candidate.full_name}» перейдут к «${target.full_name}». Эта запись останется в архиве как объединённая.` : ''}
        confirmLabel="Объединить"
        isLoading={merge.isPending}
        onConfirm={() => void doMerge()}
        onCancel={() => setTarget(null)}
      />
    </Card>
  )
}

function NotesList({ candidateId }: { candidateId: number }) {
  const notes = useCandidateNotes(candidateId)
  if (notes.isPending) return <LoadingState />
  if (notes.isError) return <ErrorState message={extractErrorMessage(notes.error)} onRetry={() => void notes.refetch()} />
  if (!notes.data.length) return <p className="mt-4 text-sm text-ink-secondary">Заметок пока нет.</p>
  return (
    <ol className="mt-4 space-y-3">
      {notes.data.map((note) => (
        <li key={note.id} className="rounded-xl bg-surface-muted px-3 py-2">
          <p className="whitespace-pre-line break-words text-sm text-ink">{note.text}</p>
          <p className="mt-1 text-xs text-ink-muted">
            {officeDateTime(note.created_at)}{note.author_info ? ` · ${note.author_info.full_name}` : ''}{note.application_number ? ` · отклик ${note.application_number}` : ''}
          </p>
        </li>
      ))}
    </ol>
  )
}

function HistoryList({ candidateId }: { candidateId: number }) {
  const history = useCandidateHistory(candidateId)
  if (history.isPending) return <LoadingState />
  if (history.isError) return <ErrorState message={extractErrorMessage(history.error)} onRetry={() => void history.refetch()} />
  return <ActivityList items={history.data} showSubject={false} />
}

function NoteForm({ candidateId, applicationId }: { candidateId: number; applicationId: number | null }) {
  const { showToast } = useToast()
  const add = useAddNote()
  const [text, setText] = useState('')
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!text.trim()) return
    try {
      await add.mutateAsync({ id: candidateId, text: text.trim(), application: applicationId })
      setText('')
      showToast('Заметка добавлена', 'success')
    } catch (err) {
      showToast(extractErrorMessage(err), 'error')
    }
  }
  return (
    <form onSubmit={submit} className="space-y-2">
      <label htmlFor="cand-note" className="sr-only">Новая заметка</label>
      <Textarea id="cand-note" rows={2} placeholder="Звонок, договорённость, впечатление…" value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} />
      <div className="flex justify-end">
        <Button type="submit" size="sm" isLoading={add.isPending} disabled={!text.trim()}>Добавить заметку</Button>
      </div>
    </form>
  )
}

function StatusForm({ application, onClose }: { application: Application; onClose: () => void }) {
  const { showToast } = useToast()
  const change = useChangeApplicationStatus()
  const [status, setStatus] = useState<ApplicationStatus | ''>('')
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!status) {
      setError('Выберите этап.')
      return
    }
    try {
      await change.mutateAsync({ id: application.id, status, comment: comment.trim() })
      showToast('Этап изменён', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <p className="text-sm text-ink-secondary">
        Сейчас: <strong>{application.status_label}</strong>. Доступны только допустимые переходы; этапы собеседований
        ставятся самими собеседованиями, «Принят на работу» — кнопкой найма. История переходов сохраняется.
      </p>
      <Field id="app-status" label="Новый этап" required>
        <Select id="app-status" value={status} onChange={(e) => setStatus(e.target.value as ApplicationStatus)} placeholder="Выберите этап" options={application.allowed_statuses} />
      </Field>
      <Field id="app-status-comment" label="Комментарий"><Textarea id="app-status-comment" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={1000} /></Field>
      {status === 'rejected' || status === 'withdrawn' || status === 'offer' ? (
        <p className="text-xs text-warning">Запланированные собеседования по этому отклику будут отменены.</p>
      ) : null}
      <FormError message={error} />
      <FormActions onCancel={onClose} isLoading={change.isPending} submitLabel="Сменить этап" />
    </form>
  )
}

function ProfileForm({ candidate, onClose }: { candidate: Candidate; onClose: () => void }) {
  const { showToast } = useToast()
  const save = useUpdateCandidate()
  const [form, setForm] = useState<PersonFields>({
    last_name: candidate.last_name, first_name: candidate.first_name, middle_name: candidate.middle_name, phone: candidate.phone,
    email: candidate.email, city: candidate.city, experience: candidate.experience, education: candidate.education,
    skills: candidate.skills, portfolio_url: candidate.portfolio_url,
  })
  const [error, setError] = useState<string | null>(null)
  const set = (key: keyof PersonFields) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!form.first_name.trim()) return setError('Укажите имя.')
    if (!form.phone.trim() && !form.email.trim()) return setError('Укажите телефон или email.')
    try {
      await save.mutateAsync({ id: candidate.id, payload: Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim()])) })
      showToast('Профиль сохранён', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field id="pf-last" label="Фамилия"><Input id="pf-last" value={form.last_name} onChange={set('last_name')} maxLength={100} /></Field>
        <Field id="pf-first" label="Имя" required><Input id="pf-first" value={form.first_name} onChange={set('first_name')} maxLength={100} /></Field>
        <Field id="pf-middle" label="Отчество"><Input id="pf-middle" value={form.middle_name} onChange={set('middle_name')} maxLength={100} /></Field>
        <Field id="pf-phone" label="Телефон"><Input id="pf-phone" type="tel" value={form.phone} onChange={set('phone')} maxLength={32} /></Field>
        <Field id="pf-email" label="Email"><Input id="pf-email" type="email" value={form.email} onChange={set('email')} /></Field>
        <Field id="pf-city" label="Город"><Input id="pf-city" value={form.city} onChange={set('city')} maxLength={100} /></Field>
      </div>
      <Field id="pf-exp" label="Опыт работы"><Textarea id="pf-exp" rows={3} value={form.experience} onChange={set('experience')} /></Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="pf-edu" label="Образование"><Textarea id="pf-edu" rows={2} value={form.education} onChange={set('education')} /></Field>
        <Field id="pf-skills" label="Навыки"><Textarea id="pf-skills" rows={2} value={form.skills} onChange={set('skills')} /></Field>
      </div>
      <Field id="pf-portfolio" label="Портфолио или профиль"><Input id="pf-portfolio" type="url" value={form.portfolio_url} onChange={set('portfolio_url')} /></Field>
      <FormError message={error} />
      <FormActions onCancel={onClose} isLoading={save.isPending} />
    </form>
  )
}

function NewApplication({ candidate, meta, onClose, onSaved }: { candidate: Candidate; meta: RecruitmentMeta; onClose: () => void; onSaved: (id: number) => void }) {
  const vacancies = useAllVacancies()
  return <ApplicationForm candidateId={candidate.id} meta={meta} vacancies={vacancies.data?.results ?? []} onClose={onClose} onSaved={(a) => onSaved(a.id)} />
}

/** Найм: роли, которыми HR управляет сам, — учётная запись создаётся сразу
 * (после подтверждения); остальные — запрос администратору. */
function HireForm({ candidate, application, meta, onClose }: { candidate: Candidate; application: Application; meta: RecruitmentMeta; onClose: () => void }) {
  const { showToast } = useToast()
  const hire = useHireCandidate()
  const request = useRequestAccount()
  const [form, setForm] = useState({
    username: '', email: candidate.email, first_name: candidate.first_name, last_name: candidate.last_name, role: '',
    password: '', password_confirm: '', comment: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const direct = meta.hire_roles.some((r) => r.value === form.role)
  const requested = meta.requestable_roles.some((r) => r.value === form.role)
  const roleLabel = [...meta.hire_roles, ...meta.requestable_roles].find((r) => r.value === form.role)?.label ?? ''

  const check = (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!form.username.trim() || !form.email.trim() || !form.first_name.trim() || !form.role) {
      return setError('Заполните логин, email, имя и должность.')
    }
    if (direct && !form.password) return setError('Задайте пароль.')
    if (direct && form.password !== form.password_confirm) return setError('Пароли не совпадают.')
    setConfirming(true)
  }
  const run = async () => {
    const base = { username: form.username.trim(), email: form.email.trim(), first_name: form.first_name.trim(), last_name: form.last_name.trim() }
    try {
      if (direct) {
        await hire.mutateAsync({ id: application.id, payload: { ...base, role: form.role as typeof meta.hire_roles[number]['value'], password: form.password, password_confirm: form.password_confirm } })
        showToast('Кандидат принят: учётная запись создана', 'success')
      } else {
        await request.mutateAsync({ id: application.id, payload: { ...base, role: form.role, comment: form.comment } })
        showToast('Запрос отправлен администратору', 'success')
      }
      onClose()
    } catch (err) {
      setConfirming(false)
      setError(extractErrorMessage(err))
    }
  }
  return (
    <form onSubmit={check} className="space-y-3" noValidate>
      <p className="text-sm text-ink-secondary">
        Учётная запись LMS создаётся обычным механизмом и связывается с откликом {application.number}. Анкета и история
        найма сохраняются; повторно принять кандидата нельзя.
      </p>
      <Field id="hire-role" label="Должность" required>
        <select id="hire-role" value={form.role} onChange={set('role')} className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-ink">
          <option value="">Выберите должность</option>
          <optgroup label="HR оформляет сам">
            {meta.hire_roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </optgroup>
          <optgroup label="Нужно согласование администратора">
            {meta.requestable_roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </optgroup>
        </select>
      </Field>
      {requested ? (
        <p className="rounded-xl bg-info-soft px-3 py-2 text-sm text-info">
          Эту должность HR не оформляет сам. Будет отправлен запрос администратору: он создаст учётную запись и задаст пароль.
        </p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="hire-first" label="Имя" required><Input id="hire-first" value={form.first_name} onChange={set('first_name')} maxLength={100} /></Field>
        <Field id="hire-last" label="Фамилия"><Input id="hire-last" value={form.last_name} onChange={set('last_name')} maxLength={100} /></Field>
        <Field id="hire-username" label="Логин" required><Input id="hire-username" value={form.username} onChange={set('username')} autoComplete="off" maxLength={150} /></Field>
        <Field id="hire-email" label="Email" required><Input id="hire-email" type="email" value={form.email} onChange={set('email')} /></Field>
      </div>
      {direct ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field id="hire-password" label="Пароль" required><Input id="hire-password" type="password" value={form.password} onChange={set('password')} autoComplete="new-password" /></Field>
          <Field id="hire-password2" label="Повторите пароль" required><Input id="hire-password2" type="password" value={form.password_confirm} onChange={set('password_confirm')} autoComplete="new-password" /></Field>
        </div>
      ) : null}
      {requested ? <Field id="hire-comment" label="Комментарий для администратора"><Textarea id="hire-comment" rows={2} value={form.comment} onChange={set('comment')} maxLength={2000} /></Field> : null}
      <FormError message={error} />
      <FormActions onCancel={onClose} isLoading={hire.isPending || request.isPending} submitLabel={requested ? 'Отправить запрос' : 'Принять на работу'} />
      <ConfirmDialog
        isOpen={confirming}
        title={requested ? 'Отправить запрос администратору?' : 'Создать учётную запись сотрудника?'}
        message={requested
          ? `Администратор получит запрос на учётную запись «${form.username.trim()}» (${roleLabel}) для ${candidate.full_name}.`
          : `Будет создана учётная запись «${form.username.trim()}» (${roleLabel}) для ${candidate.full_name}, этап отклика станет «Принят на работу». Отменить это действие нельзя.`}
        confirmLabel={requested ? 'Отправить' : 'Создать и принять'}
        isLoading={hire.isPending || request.isPending}
        onConfirm={() => void run()}
        onCancel={() => setConfirming(false)}
      />
    </form>
  )
}

function EraseDialog({ candidate, isOpen, onClose }: { candidate: Candidate; isOpen: boolean; onClose: () => void }) {
  const erase = useEraseCandidate()
  const { showToast } = useToast()
  const run = async () => {
    try {
      await erase.mutateAsync({ id: candidate.id, reason: 'Запрос кандидата или истёк срок хранения' })
      showToast('Персональные данные удалены', 'success')
      onClose()
    } catch (err) {
      showToast(extractErrorMessage(err), 'error')
      onClose()
    }
  }
  return (
    <ConfirmDialog
      isOpen={isOpen}
      tone="danger"
      title="Удалить персональные данные?"
      message="ФИО, контакты, анкета, письма, резюме и заметки будут стёрты без возможности восстановления. Отклики, этапы и даты останутся только для статистики. Доступно для кандидатов без действующих откликов и без найма."
      confirmLabel="Удалить данные"
      isLoading={erase.isPending}
      onConfirm={() => void run()}
      onCancel={onClose}
    />
  )
}

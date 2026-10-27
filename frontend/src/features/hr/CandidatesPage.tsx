import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import { AlertTriangle, Paperclip, Plus, UserSearch, Users } from 'lucide-react'
import { isAxiosError } from 'axios'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import {
  useAllVacancies, useApplications, useBoard, useCandidatesList, useChangeApplicationStatus, useCreateApplication,
  useRecruitmentMeta,
} from '@/hooks/useHr'
import { useAuth } from '@/hooks/useAuth'
import { extractErrorMessage } from '@/lib/apiError'
import type { Application, ApplicationInput, ApplicationSource, ApplicationsParams, DuplicateMatch, RecruitmentMeta, Vacancy } from '@/types/hr'
import { cn } from '@/utils/cn'
import { formatDateShort } from '@/utils/format'

import {
  ApplicationStatusBadge, Field, FormActions, FormError, SortableTh, TABLE_HEAD, Th, candidatePath, officeDateTime,
} from './shared'

const PAGE_SIZE = 20
type View = 'table' | 'board' | 'people'

/** /hr/candidates — отклики: таблица с фильтрами, доска этапов найма и база
 * людей. У одного кандидата может быть несколько откликов на разные вакансии. */
export function HrCandidatesPage() {
  const meta = useRecruitmentMeta()
  const vacancies = useAllVacancies()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const view = (params.get('view') as View | null) ?? 'table'
  const [filters, setFilters] = useState({
    search: '', status: params.get('status') ?? '', vacancy: params.get('vacancy') ?? '', source: '', responsible: '',
    date_from: '', date_to: '', active: false, duplicates: params.get('duplicates') === 'true',
  })
  const [ordering, setOrdering] = useState('-created_at')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const query: ApplicationsParams = {
    search: filters.search.trim() || undefined, status: filters.status || undefined, vacancy: filters.vacancy || undefined,
    source: filters.source || undefined, responsible: filters.responsible || undefined,
    date_from: filters.date_from || undefined, date_to: filters.date_to || undefined,
    active: filters.active ? 'true' : undefined, duplicates: filters.duplicates ? 'true' : undefined,
  }
  const list = useApplications({ ...query, ordering, page }, view === 'table')
  const set = (key: keyof typeof filters) => (value: string | boolean) => {
    setFilters((f) => ({ ...f, [key]: value }))
    setPage(1)
  }
  const setView = (value: View) => {
    const next = new URLSearchParams(params)
    next.set('view', value)
    setParams(next, { replace: true })
  }
  const sort = (value: string) => {
    setOrdering(value)
    setPage(1)
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Кандидаты"
        description="Отклики с сайта и добавленные вручную; этапы найма"
        actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setCreating(true)}>Добавить кандидата</Button>}
      />
      <SegmentedControl aria-label="Вид" value={view} onChange={setView}
        options={[{ value: 'table', label: 'Таблица' }, { value: 'board', label: 'Доска этапов' }, { value: 'people', label: 'Люди' }]} />

      {view === 'people' ? <PeopleList /> : (
        <>
          <Card>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <SearchInput value={filters.search} onChange={set('search')} placeholder="ФИО, телефон, email, номер заявки" aria-label="Поиск кандидата" />
              {view === 'table' ? (
                <Select aria-label="Этап" value={filters.status} onChange={(e) => set('status')(e.target.value)} placeholder="Все этапы" options={meta.data?.application_statuses ?? []} />
              ) : null}
              <Select aria-label="Вакансия" value={filters.vacancy} onChange={(e) => set('vacancy')(e.target.value)} placeholder="Все вакансии" options={(vacancies.data?.results ?? []).map((v) => ({ value: String(v.id), label: v.title }))} />
              <Select aria-label="Источник" value={filters.source} onChange={(e) => set('source')(e.target.value)} placeholder="Все источники" options={meta.data?.sources ?? []} />
              <Select aria-label="Ответственный" value={filters.responsible} onChange={(e) => set('responsible')(e.target.value)} placeholder="Все ответственные" options={(meta.data?.people ?? []).map((p) => ({ value: String(p.id), label: p.full_name }))} />
              <label className="text-sm"><span className="mb-1 block field-label">Отклик с</span>
                <DatePicker aria-label="Дата отклика с" value={filters.date_from} onChange={(e) => set('date_from')(e.target.value)} />
              </label>
              <label className="text-sm"><span className="mb-1 block field-label">по</span>
                <DatePicker aria-label="Дата отклика по" value={filters.date_to} onChange={(e) => set('date_to')(e.target.value)} />
              </label>
              <div className="flex flex-col justify-end gap-2 text-sm text-ink">
                {view === 'table' ? (
                  <label className="flex items-center gap-2">
                    <input type="checkbox" className="size-4 accent-brand-600" checked={filters.active} onChange={(e) => set('active')(e.target.checked)} />
                    Только в работе
                  </label>
                ) : null}
                <label className="flex items-center gap-2">
                  <input type="checkbox" className="size-4 accent-brand-600" checked={filters.duplicates} onChange={(e) => set('duplicates')(e.target.checked)} />
                  Проверить на дубль
                </label>
              </div>
            </div>
          </Card>
          {view === 'board' ? <Board query={query} /> : list.isPending ? (
            <LoadingState />
          ) : list.isError ? (
            <ErrorState message={extractErrorMessage(list.error)} onRetry={() => void list.refetch()} />
          ) : list.data.results.length === 0 ? (
            <EmptyState icon={UserSearch} title="Откликов не найдено" description="Измените фильтры или добавьте кандидата вручную." />
          ) : (
            <Card padding="none" className="overflow-x-auto">
              <table className="w-full min-w-[920px] text-sm">
                <thead className={TABLE_HEAD}>
                  <tr>
                    <SortableTh label="Кандидат" field="candidate__last_name" ordering={ordering} onChange={sort} />
                    <Th>Вакансия</Th>
                    <SortableTh label="Этап" field="status" ordering={ordering} onChange={sort} />
                    <Th>Ближайшая встреча</Th>
                    <Th>Источник</Th>
                    <Th>Ответственный</Th>
                    <SortableTh label="Отклик" field="created_at" ordering={ordering} onChange={sort} />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {list.data.results.map((a) => (
                    <tr key={a.id} className="cursor-pointer hover:bg-surface-hover" onClick={() => navigate(candidatePath(a.candidate, a.id))}>
                      <td className="px-4 py-3">
                        <Link to={candidatePath(a.candidate, a.id)} className="font-medium text-ink hover:text-brand-700" onClick={(e) => e.stopPropagation()}>{a.candidate_info.full_name}</Link>
                        <p className="text-xs text-ink-secondary">{[a.candidate_info.phone, a.candidate_info.email].filter(Boolean).join(' · ')}</p>
                        {a.needs_duplicate_review ? <Badge tone="warning" className="mt-1">Проверить дубль</Badge> : null}
                      </td>
                      <td className="px-4 py-3">
                        {a.position_label || '—'}
                        <p className="text-xs text-ink-muted">{a.number}</p>
                      </td>
                      <td className="px-4 py-3"><ApplicationStatusBadge status={a.status} label={a.status_label} /></td>
                      <td className="px-4 py-3 tabular-nums">{a.next_interview_at ? officeDateTime(a.next_interview_at) : '—'}</td>
                      <td className="px-4 py-3">{a.source_label}{a.channel === 'public' ? <span className="block text-xs text-ink-muted">с сайта</span> : null}</td>
                      <td className="px-4 py-3">{a.responsible_info?.full_name ?? '—'}</td>
                      <td className="px-4 py-3 tabular-nums">{formatDateShort(a.applied_on)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
          {view === 'table' && list.data ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={list.data.count} onPageChange={setPage} /> : null}
        </>
      )}
      <Modal isOpen={creating} onClose={() => setCreating(false)} title="Добавить кандидата" size="lg">
        {creating && meta.data ? (
          <ApplicationForm meta={meta.data} vacancies={vacancies.data?.results ?? []} onClose={() => setCreating(false)}
            onSaved={(saved) => navigate(candidatePath(saved.candidate, saved.id))} />
        ) : null}
      </Modal>
    </div>
  )
}

/** Доска этапов: карточку можно перетащить в соседний допустимый этап (или
 * выбрать этап в меню карточки). Этапы собеседований и найма ставятся только
 * соответствующими действиями — на доске они недоступны для перетаскивания. */
function Board({ query }: { query: ApplicationsParams }) {
  const board = useBoard(query)
  const change = useChangeApplicationStatus()
  const { showToast } = useToast()
  const [dragged, setDragged] = useState<Application | null>(null)
  const move = async (application: Application, status: string) => {
    if (status === application.status) return
    if (!application.allowed_statuses.some((s) => s.value === status)) {
      showToast('Этот переход недоступен с текущего этапа', 'error')
      return
    }
    try {
      await change.mutateAsync({ id: application.id, status, comment: '' })
      showToast('Этап изменён', 'success')
    } catch (err) {
      showToast(extractErrorMessage(err), 'error')
    }
  }
  if (board.isPending) return <LoadingState label="Загружаем доску…" />
  if (board.isError) return <ErrorState message={extractErrorMessage(board.error)} onRetry={() => void board.refetch()} />
  return (
    <div className="scroll-x -mx-4 px-4 pb-2 sm:mx-0 sm:px-0">
      <div className="flex gap-3">
        {board.data.columns.map((column) => {
          const canDrop = dragged ? dragged.allowed_statuses.some((s) => s.value === column.status) : false
          return (
            <section
              key={column.status}
              aria-label={column.label}
              className={cn('flex w-64 shrink-0 flex-col rounded-xl border bg-surface-muted p-2', canDrop ? 'border-brand-500 bg-brand-50' : 'border-border')}
              onDragOver={(e: DragEvent) => { if (canDrop) e.preventDefault() }}
              onDrop={(e: DragEvent) => { e.preventDefault(); if (dragged) void move(dragged, column.status); setDragged(null) }}
            >
              <header className="mb-2 flex items-center justify-between px-1">
                <h3 className="text-sm font-semibold text-ink">{column.label}</h3>
                <span className="rounded-full bg-surface px-2 text-xs tabular-nums text-ink-secondary">{column.count}</span>
              </header>
              <div className="space-y-2">
                {column.items.map((a) => (
                  <article
                    key={a.id}
                    draggable={a.allowed_statuses.length > 0}
                    onDragStart={() => setDragged(a)}
                    onDragEnd={() => setDragged(null)}
                    className="rounded-lg border border-border bg-surface p-2.5 shadow-sm"
                  >
                    <Link to={candidatePath(a.candidate, a.id)} className="block text-sm font-medium text-ink hover:text-brand-700">{a.candidate_info.full_name}</Link>
                    <p className="text-xs text-ink-secondary">{a.position_label || '—'}</p>
                    <p className="text-xs text-ink-muted">{formatDateShort(a.applied_on)}{a.next_interview_at ? ` · встреча ${officeDateTime(a.next_interview_at)}` : ''}</p>
                    {a.needs_duplicate_review ? <Badge tone="warning" className="mt-1">Дубль?</Badge> : null}
                    {a.allowed_statuses.length ? (
                      <select
                        aria-label={`Перевести «${a.candidate_info.full_name}» в этап`}
                        className="mt-2 h-8 w-full rounded-md border border-border bg-surface px-2 text-xs text-ink-secondary"
                        value=""
                        onChange={(e) => void move(a, e.target.value)}
                      >
                        <option value="">Перевести в этап…</option>
                        {a.allowed_statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                      </select>
                    ) : null}
                  </article>
                ))}
                {column.count > column.items.length ? (
                  <p className="px-1 text-xs text-ink-muted">и ещё {column.count - column.items.length} — уточните фильтры</p>
                ) : null}
                {column.count === 0 ? <p className="px-1 py-3 text-center text-xs text-ink-muted">Пусто</p> : null}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}

function PeopleList() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const people = useCandidatesList({ search: search.trim() || undefined, page })
  return (
    <>
      <Card>
        <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="ФИО, телефон или email" aria-label="Поиск человека" />
      </Card>
      {people.isPending ? <LoadingState /> : people.isError ? (
        <ErrorState message={extractErrorMessage(people.error)} onRetry={() => void people.refetch()} />
      ) : people.data.results.length === 0 ? (
        <EmptyState icon={Users} title="Никого не найдено" />
      ) : (
        <Card padding="none" className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className={TABLE_HEAD}><tr><Th>Кандидат</Th><Th>Контакты</Th><Th>Город</Th><Th>Откликов</Th><Th>Последний отклик</Th></tr></thead>
            <tbody className="divide-y divide-border">
              {people.data.results.map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-3"><Link className="font-medium text-ink hover:text-brand-700" to={candidatePath(p.id)}>{p.full_name}</Link></td>
                  <td className="px-4 py-3 text-ink-secondary">{[p.phone, p.email].filter(Boolean).join(' · ') || '—'}</td>
                  <td className="px-4 py-3">{p.city || '—'}</td>
                  <td className="px-4 py-3 tabular-nums">{p.applications_count}{p.active_count ? <span className="text-ink-muted"> · в работе {p.active_count}</span> : null}</td>
                  <td className="px-4 py-3 tabular-nums">{p.last_applied_on ? formatDateShort(p.last_applied_on) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {people.data ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={people.data.count} onPageChange={setPage} /> : null}
    </>
  )
}

function matchesOf(error: unknown): DuplicateMatch[] | null {
  if (!isAxiosError(error) || error.response?.status !== 409) return null
  const data = error.response.data as { code?: string; matches?: DuplicateMatch[] }
  return data.code === 'possible_duplicates' ? data.matches ?? [] : null
}

/** Кандидат, добавленный HR. При совпадении контактов сервер не создаёт
 * человека молча — HR выбирает существующего кандидата или подтверждает, что
 * это другой человек. */
export function ApplicationForm({ meta, vacancies, onClose, onSaved, candidateId }: {
  meta: RecruitmentMeta
  vacancies: Vacancy[]
  onClose: () => void
  onSaved?: (application: Application) => void
  /** Новый отклик существующего кандидата: поля человека не нужны. */
  candidateId?: number
}) {
  const { user } = useAuth()
  const { showToast } = useToast()
  const create = useCreateApplication()
  const fileInput = useRef<HTMLInputElement>(null)
  const [resume, setResume] = useState<File | null>(null)
  const [form, setForm] = useState({
    last_name: '', first_name: '', middle_name: '', phone: '', email: '', city: '', vacancy: '', position: '',
    source: 'job_site' as ApplicationSource, source_details: '', applied_on: meta.today, responsible: String(user?.id ?? ''),
    cover_letter: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [matches, setMatches] = useState<DuplicateMatch[] | null>(null)
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))
  // Новые кандидаты — только на действующие вакансии (не закрытые и не в архиве).
  const vacancyOptions = vacancies
    .filter((v) => ['draft', 'published', 'paused'].includes(v.status))
    .map((v) => ({ value: String(v.id), label: v.status === 'published' ? v.title : `${v.title} (${v.status_label.toLowerCase()})` }))

  const submit = async (options: { candidate?: number; confirmNew?: boolean } = {}) => {
    setError(null)
    const existing = options.candidate ?? candidateId
    const missing = []
    if (!existing) {
      if (!form.first_name.trim()) missing.push('имя')
      if (!form.phone.trim() && !form.email.trim()) missing.push('телефон или email')
    }
    if (!form.vacancy && !form.position.trim()) missing.push('вакансию или должность')
    if (missing.length) {
      setError(`Укажите ${missing.join(', ')}.`)
      return
    }
    const payload: ApplicationInput = {
      vacancy: form.vacancy ? Number(form.vacancy) : null, position: form.position.trim(), source: form.source,
      source_details: form.source_details.trim(), applied_on: form.applied_on,
      responsible: form.responsible ? Number(form.responsible) : null, cover_letter: form.cover_letter,
      ...(existing ? { candidate: existing } : {
        last_name: form.last_name.trim(), first_name: form.first_name.trim(), middle_name: form.middle_name.trim(),
        phone: form.phone.trim(), email: form.email.trim(), city: form.city.trim(), confirm_new: options.confirmNew ?? false,
      }),
    }
    try {
      const saved = await create.mutateAsync({ payload, resume })
      showToast('Отклик добавлен', 'success')
      onClose()
      onSaved?.(saved)
    } catch (err) {
      const found = matchesOf(err)
      if (found) setMatches(found)
      else setError(extractErrorMessage(err))
    }
  }

  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); void submit() }} className="space-y-3" noValidate>
      {candidateId ? null : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field id="app-last" label="Фамилия"><Input id="app-last" value={form.last_name} onChange={set('last_name')} maxLength={100} /></Field>
            <Field id="app-first" label="Имя" required><Input id="app-first" value={form.first_name} onChange={set('first_name')} maxLength={100} /></Field>
            <Field id="app-middle" label="Отчество"><Input id="app-middle" value={form.middle_name} onChange={set('middle_name')} maxLength={100} /></Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field id="app-phone" label="Телефон" hint="Телефон или email — обязательно одно из двух"><Input id="app-phone" type="tel" value={form.phone} onChange={(e) => { set('phone')(e); setMatches(null) }} maxLength={32} /></Field>
            <Field id="app-email" label="Email"><Input id="app-email" type="email" value={form.email} onChange={(e) => { set('email')(e); setMatches(null) }} /></Field>
            <Field id="app-city" label="Город"><Input id="app-city" value={form.city} onChange={set('city')} maxLength={100} /></Field>
          </div>
        </>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="app-vacancy" label="Вакансия"><Select id="app-vacancy" value={form.vacancy} onChange={set('vacancy')} placeholder="Без вакансии" options={vacancyOptions} /></Field>
        <Field id="app-position" label="Должность" hint="Если кандидат не на конкретную вакансию"><Input id="app-position" value={form.position} onChange={set('position')} maxLength={150} /></Field>
        <Field id="app-source" label="Источник" required><Select id="app-source" value={form.source} onChange={set('source')} options={meta.sources} /></Field>
        <Field id="app-source-details" label="Источник — подробнее"><Input id="app-source-details" value={form.source_details} onChange={set('source_details')} maxLength={255} /></Field>
        <Field id="app-date" label="Дата отклика" required><DatePicker id="app-date" value={form.applied_on} max={meta.today} onChange={set('applied_on')} /></Field>
        <Field id="app-resp" label="Ответственный">
          <Select id="app-resp" value={form.responsible} onChange={set('responsible')} placeholder="Не назначен" options={meta.people.map((p) => ({ value: String(p.id), label: `${p.full_name} · ${p.role_label}` }))} />
        </Field>
      </div>
      <Field id="app-letter" label="Сопроводительное письмо / комментарий"><Textarea id="app-letter" rows={3} value={form.cover_letter} onChange={set('cover_letter')} maxLength={5000} /></Field>
      <div>
        <input ref={fileInput} type="file" className="sr-only" id="app-resume" accept=".pdf,.docx" onChange={(e) => setResume(e.target.files?.[0] ?? null)} />
        <Button type="button" size="sm" variant="secondary" leftIcon={<Paperclip className="size-4" aria-hidden />} onClick={() => fileInput.current?.click()}>
          {resume ? resume.name : `Прикрепить резюме (PDF/DOCX, до ${meta.resume_max_mb} МБ)`}
        </Button>
      </div>
      {matches ? (
        <div className="space-y-2 rounded-xl bg-warning-soft px-3 py-2 text-sm text-warning" role="alert">
          <p className="flex items-center gap-2 font-medium"><AlertTriangle className="size-4" aria-hidden />Кандидат с такими контактами уже есть</p>
          <ul className="space-y-1.5">
            {matches.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 text-ink">
                <span>
                  <Link className="font-medium hover:underline" to={candidatePath(m.id)} target="_blank">{m.full_name}</Link>
                  <span className="text-ink-secondary"> · {[m.same_phone ? 'тот же телефон' : '', m.same_email ? 'тот же email' : ''].filter(Boolean).join(', ')} · откликов: {m.applications}</span>
                </span>
                <Button type="button" size="sm" variant="secondary" isLoading={create.isPending} onClick={() => void submit({ candidate: m.id })}>Это он — добавить отклик</Button>
              </li>
            ))}
          </ul>
          <Button type="button" size="sm" variant="ghost" isLoading={create.isPending} onClick={() => void submit({ confirmNew: true })}>Это другой человек</Button>
        </div>
      ) : null}
      <FormError message={error} />
      <FormActions onCancel={onClose} isLoading={create.isPending} submitLabel="Добавить" />
    </form>
  )
}

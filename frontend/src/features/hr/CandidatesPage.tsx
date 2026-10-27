import { useState, type FormEvent } from 'react'
import { Plus, UserSearch } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
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
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useAllVacancies, useCandidates, useRecruitmentMeta, useSaveCandidate } from '@/hooks/useHr'
import { useAuth } from '@/hooks/useAuth'
import { extractErrorMessage } from '@/lib/apiError'
import type { Candidate, CandidateInput, CandidateSource, RecruitmentMeta, Vacancy } from '@/types/hr'
import { formatDateShort } from '@/utils/format'

import { CandidateStatusBadge, Field, FormActions, FormError, officeDateTime, SortableTh, TABLE_HEAD, Th } from './shared'

const PAGE_SIZE = 20

/** /hr/candidates — кандидаты: поиск, фильтры по этапу, вакансии, источнику и
 * ответственному, сортировка, добавление. */
export function HrCandidatesPage() {
  const meta = useRecruitmentMeta()
  const vacancies = useAllVacancies()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [filters, setFilters] = useState({
    search: '', status: '', vacancy: params.get('vacancy') ?? '', source: '', responsible: '', active: false,
  })
  const [ordering, setOrdering] = useState('-added_on')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const list = useCandidates({
    search: filters.search.trim() || undefined, status: filters.status || undefined, vacancy: filters.vacancy || undefined,
    source: filters.source || undefined, responsible: filters.responsible || undefined,
    active: filters.active ? 'true' : undefined, ordering, page,
  })
  const set = (key: keyof typeof filters) => (value: string | boolean) => {
    setFilters((f) => ({ ...f, [key]: value }))
    setPage(1)
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Кандидаты"
        description="Учёт кандидатов и этапов найма"
        actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setCreating(true)}>Новый кандидат</Button>}
      />
      <Card>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <SearchInput value={filters.search} onChange={set('search')} placeholder="ФИО, телефон, email, должность" aria-label="Поиск кандидата" />
          <Select aria-label="Этап" value={filters.status} onChange={(e) => set('status')(e.target.value)} placeholder="Все этапы" options={meta.data?.candidate_statuses ?? []} />
          <Select aria-label="Вакансия" value={filters.vacancy} onChange={(e) => set('vacancy')(e.target.value)} placeholder="Все вакансии" options={(vacancies.data?.results ?? []).map((v) => ({ value: String(v.id), label: v.title }))} />
          <Select aria-label="Источник" value={filters.source} onChange={(e) => set('source')(e.target.value)} placeholder="Все источники" options={meta.data?.sources ?? []} />
          <Select aria-label="Ответственный" value={filters.responsible} onChange={(e) => set('responsible')(e.target.value)} placeholder="Все ответственные" options={(meta.data?.people ?? []).map((p) => ({ value: String(p.id), label: p.full_name }))} />
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" className="size-4 accent-brand-600" checked={filters.active} onChange={(e) => set('active')(e.target.checked)} />
            Только в работе (без принятых и закрытых)
          </label>
        </div>
      </Card>
      {list.isPending ? (
        <LoadingState />
      ) : list.isError ? (
        <ErrorState message={extractErrorMessage(list.error)} onRetry={() => void list.refetch()} />
      ) : list.data.results.length === 0 ? (
        <EmptyState icon={UserSearch} title="Кандидатов не найдено" description="Измените фильтры или добавьте кандидата." />
      ) : (
        <Card padding="none" className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead className={TABLE_HEAD}>
              <tr>
                <SortableTh label="Кандидат" field="last_name" ordering={ordering} onChange={(v) => { setOrdering(v); setPage(1) }} />
                <Th>Вакансия / должность</Th>
                <SortableTh label="Этап" field="status" ordering={ordering} onChange={(v) => { setOrdering(v); setPage(1) }} />
                <Th>Ближайшая встреча</Th>
                <Th>Источник</Th>
                <Th>Ответственный</Th>
                <SortableTh label="Добавлен" field="added_on" ordering={ordering} onChange={(v) => { setOrdering(v); setPage(1) }} />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.data.results.map((c) => (
                <tr key={c.id} className="cursor-pointer hover:bg-surface-hover" onClick={() => navigate(`/hr/candidates/${c.id}`)}>
                  <td className="px-4 py-3">
                    <Link to={`/hr/candidates/${c.id}`} className="font-medium text-ink hover:text-brand-700" onClick={(e) => e.stopPropagation()}>{c.full_name}</Link>
                    <p className="text-xs text-ink-secondary">{[c.phone, c.email].filter(Boolean).join(' · ')}</p>
                  </td>
                  <td className="px-4 py-3">{c.position_label || '—'}</td>
                  <td className="px-4 py-3"><CandidateStatusBadge status={c.status} label={c.status_label} /></td>
                  <td className="px-4 py-3 tabular-nums">{c.next_interview_at ? officeDateTime(c.next_interview_at) : '—'}</td>
                  <td className="px-4 py-3">{c.source_label}</td>
                  <td className="px-4 py-3">{c.responsible_info?.full_name ?? '—'}</td>
                  <td className="px-4 py-3 tabular-nums">{formatDateShort(c.added_on)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {list.data ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={list.data.count} onPageChange={setPage} /> : null}
      <Modal isOpen={creating} onClose={() => setCreating(false)} title="Новый кандидат">
        {creating && meta.data ? (
          <CandidateForm
            candidate={null}
            meta={meta.data}
            vacancies={vacancies.data?.results ?? []}
            onClose={() => setCreating(false)}
            onSaved={(saved) => navigate(`/hr/candidates/${saved.id}`)}
          />
        ) : null}
      </Modal>
    </div>
  )
}

export function CandidateForm({ candidate, meta, vacancies, onClose, onSaved }: {
  candidate: Candidate | null
  meta: RecruitmentMeta
  vacancies: Vacancy[]
  onClose: () => void
  onSaved?: (candidate: Candidate) => void
}) {
  const { user } = useAuth()
  const { showToast } = useToast()
  const save = useSaveCandidate()
  const [form, setForm] = useState({
    last_name: candidate?.last_name ?? '',
    first_name: candidate?.first_name ?? '',
    middle_name: candidate?.middle_name ?? '',
    phone: candidate?.phone ?? '',
    email: candidate?.email ?? '',
    vacancy: candidate?.vacancy ? String(candidate.vacancy) : '',
    position: candidate?.position ?? '',
    source: candidate?.source ?? ('job_site' as CandidateSource),
    source_details: candidate?.source_details ?? '',
    added_on: candidate?.added_on ?? meta.today,
    responsible: candidate ? (candidate.responsible ? String(candidate.responsible) : '') : String(user?.id ?? ''),
    notes: candidate?.notes ?? '',
  })
  const [error, setError] = useState<string | null>(null)
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))
  // Новому кандидату — только открытые вакансии; текущая остаётся в списке.
  const vacancyOptions = vacancies
    .filter((v) => v.status === 'open' || v.id === candidate?.vacancy)
    .map((v) => ({ value: String(v.id), label: v.status === 'open' ? v.title : `${v.title} (${v.status_label.toLowerCase()})` }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    const missing = []
    if (!form.last_name.trim()) missing.push('фамилию')
    if (!form.first_name.trim()) missing.push('имя')
    if (!form.phone.trim() && !form.email.trim()) missing.push('телефон или email')
    if (!form.vacancy && !form.position.trim()) missing.push('вакансию или должность')
    if (missing.length) {
      setError(`Укажите ${missing.join(', ')}.`)
      return
    }
    const payload: CandidateInput = {
      last_name: form.last_name.trim(), first_name: form.first_name.trim(), middle_name: form.middle_name.trim(),
      phone: form.phone.trim(), email: form.email.trim(), vacancy: form.vacancy ? Number(form.vacancy) : null,
      position: form.position.trim(), source: form.source, source_details: form.source_details.trim(),
      added_on: form.added_on, responsible: form.responsible ? Number(form.responsible) : null, notes: form.notes,
    }
    try {
      const saved = await save.mutateAsync({ id: candidate?.id, payload })
      showToast(candidate ? 'Данные кандидата сохранены' : 'Кандидат добавлен', 'success')
      onClose()
      onSaved?.(saved)
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field id="cand-last" label="Фамилия" required><Input id="cand-last" value={form.last_name} onChange={set('last_name')} maxLength={100} /></Field>
        <Field id="cand-first" label="Имя" required><Input id="cand-first" value={form.first_name} onChange={set('first_name')} maxLength={100} /></Field>
        <Field id="cand-middle" label="Отчество"><Input id="cand-middle" value={form.middle_name} onChange={set('middle_name')} maxLength={100} /></Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="cand-phone" label="Телефон" hint="Телефон или email — обязательно одно из двух"><Input id="cand-phone" type="tel" value={form.phone} onChange={set('phone')} maxLength={32} /></Field>
        <Field id="cand-email" label="Email"><Input id="cand-email" type="email" value={form.email} onChange={set('email')} /></Field>
        <Field id="cand-vacancy" label="Вакансия">
          <Select id="cand-vacancy" value={form.vacancy} onChange={set('vacancy')} placeholder="Без вакансии" options={vacancyOptions} />
        </Field>
        <Field id="cand-position" label="Должность" hint="Если кандидат не на конкретную вакансию"><Input id="cand-position" value={form.position} onChange={set('position')} maxLength={150} /></Field>
        <Field id="cand-source" label="Источник" required><Select id="cand-source" value={form.source} onChange={set('source')} options={meta.sources} /></Field>
        <Field id="cand-source-details" label="Источник — подробнее"><Input id="cand-source-details" value={form.source_details} onChange={set('source_details')} maxLength={255} /></Field>
        <Field id="cand-added" label="Дата добавления" required><DatePicker id="cand-added" value={form.added_on} max={meta.today} onChange={set('added_on')} /></Field>
        <Field id="cand-resp" label="Ответственный">
          <Select id="cand-resp" value={form.responsible} onChange={set('responsible')} placeholder="Не назначен" options={meta.people.map((p) => ({ value: String(p.id), label: `${p.full_name} · ${p.role_label}` }))} />
        </Field>
      </div>
      <Field id="cand-notes" label="Заметки"><Textarea id="cand-notes" rows={3} value={form.notes} onChange={set('notes')} /></Field>
      <FormError message={error} />
      <FormActions onCancel={onClose} isLoading={save.isPending} />
    </form>
  )
}

import { useState, type FormEvent } from 'react'
import { Briefcase, PencilLine, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
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
import { useRecruitmentMeta, useSaveVacancy, useVacancies } from '@/hooks/useHr'
import { extractErrorMessage } from '@/lib/apiError'
import type { HRPerson, Vacancy, VacancyStatus } from '@/types/hr'
import { formatDateShort } from '@/utils/format'

import { Field, FormActions, FormError, officeDate, TABLE_HEAD, Th, VACANCY_TONE } from './shared'

const PAGE_SIZE = 20

/** /hr/vacancies — справочник вакансий: название, отдел, статус, ответственный. */
export function HrVacanciesPage() {
  const meta = useRecruitmentMeta()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const list = useVacancies({ search: search.trim() || undefined, status: status || undefined, page })
  const [editing, setEditing] = useState<Vacancy | 'new' | null>(null)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Вакансии"
        description="Открытые позиции, на которые подбираются кандидаты"
        actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing('new')}>Новая вакансия</Button>}
      />
      <Card>
        <div className="grid gap-3 sm:grid-cols-2">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Название или отдел" aria-label="Поиск вакансии" />
          <Select aria-label="Статус вакансии" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} placeholder="Все статусы" options={meta.data?.vacancy_statuses ?? []} />
        </div>
      </Card>
      {list.isPending ? (
        <LoadingState />
      ) : list.isError ? (
        <ErrorState message={extractErrorMessage(list.error)} onRetry={() => void list.refetch()} />
      ) : list.data.results.length === 0 ? (
        <EmptyState icon={Briefcase} title="Вакансий нет" description="Создайте вакансию, чтобы привязывать к ней кандидатов." />
      ) : (
        <Card padding="none" className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className={TABLE_HEAD}>
              <tr>
                <Th>Вакансия</Th>
                <Th>Статус</Th>
                <Th>Ответственный</Th>
                <Th>Кандидатов</Th>
                <Th>Создана</Th>
                <Th className="px-4 py-3 text-right">Действия</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.data.results.map((vacancy) => (
                <tr key={vacancy.id}>
                  <td className="px-4 py-3">
                    <p className="font-medium text-ink">{vacancy.title}</p>
                    {vacancy.department ? <p className="text-xs text-ink-secondary">{vacancy.department}</p> : null}
                  </td>
                  <td className="px-4 py-3"><Badge tone={VACANCY_TONE[vacancy.status]}>{vacancy.status_label}</Badge></td>
                  <td className="px-4 py-3">{vacancy.responsible_info?.full_name ?? '—'}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {vacancy.candidates_count ? (
                      <Link className="text-brand-700 hover:underline" to={`/hr/candidates?vacancy=${vacancy.id}`}>{vacancy.candidates_count}</Link>
                    ) : 0}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{formatDateShort(officeDate(vacancy.created_at))}</td>
                  <td className="px-4 py-3 text-right">
                    <Button size="sm" variant="ghost" aria-label={`Изменить ${vacancy.title}`} leftIcon={<PencilLine className="size-4" aria-hidden />} onClick={() => setEditing(vacancy)}>Изменить</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {list.data ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={list.data.count} onPageChange={setPage} /> : null}
      <Modal isOpen={editing !== null} onClose={() => setEditing(null)} title={editing === 'new' ? 'Новая вакансия' : 'Изменить вакансию'}>
        {editing !== null ? (
          <VacancyForm vacancy={editing === 'new' ? null : editing} statuses={meta.data?.vacancy_statuses ?? []} people={meta.data?.people ?? []} onClose={() => setEditing(null)} />
        ) : null}
      </Modal>
    </div>
  )
}

function VacancyForm({ vacancy, statuses, people, onClose }: { vacancy: Vacancy | null; statuses: { value: VacancyStatus; label: string }[]; people: HRPerson[]; onClose: () => void }) {
  const { showToast } = useToast()
  const save = useSaveVacancy()
  const [form, setForm] = useState({
    title: vacancy?.title ?? '',
    department: vacancy?.department ?? '',
    description: vacancy?.description ?? '',
    status: vacancy?.status ?? ('open' as VacancyStatus),
    responsible: vacancy?.responsible ? String(vacancy.responsible) : '',
  })
  const [error, setError] = useState<string | null>(null)
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!form.title.trim()) {
      setError('Укажите название вакансии.')
      return
    }
    try {
      await save.mutateAsync({
        id: vacancy?.id,
        payload: {
          title: form.title.trim(), department: form.department.trim(), description: form.description.trim(),
          status: form.status, responsible: form.responsible ? Number(form.responsible) : null,
        },
      })
      showToast(vacancy ? 'Вакансия сохранена' : 'Вакансия создана', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <Field id="vac-title" label="Название" required><Input id="vac-title" value={form.title} onChange={set('title')} maxLength={200} /></Field>
      <Field id="vac-dep" label="Отдел или должность"><Input id="vac-dep" value={form.department} onChange={set('department')} maxLength={150} /></Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="vac-status" label="Статус" required><Select id="vac-status" value={form.status} onChange={set('status')} options={statuses} /></Field>
        <Field id="vac-resp" label="Ответственный">
          <Select id="vac-resp" value={form.responsible} onChange={set('responsible')} placeholder="Не назначен" options={people.map((p) => ({ value: String(p.id), label: `${p.full_name} · ${p.role_label}` }))} />
        </Field>
      </div>
      <Field id="vac-desc" label="Описание"><Textarea id="vac-desc" rows={4} value={form.description} onChange={set('description')} /></Field>
      <FormError message={error} />
      <FormActions onCancel={onClose} isLoading={save.isPending} />
    </form>
  )
}

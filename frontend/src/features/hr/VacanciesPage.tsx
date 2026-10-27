import { useState } from 'react'
import { Archive, Briefcase, ExternalLink, Lock, Pause, PencilLine, Play, Plus, Send } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Menu, type MenuItem } from '@/components/ui/Menu'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { useRecruitmentMeta, useVacancies, useVacancyStatus } from '@/hooks/useHr'
import { extractErrorMessage } from '@/lib/apiError'
import type { Vacancy, VacancyStatus } from '@/types/hr'
import { formatDateShort } from '@/utils/format'

import { SortableTh, TABLE_HEAD, Th, VACANCY_TONE, officeDate } from './shared'

const PAGE_SIZE = 20

/** Действия со статусом вакансии и их подтверждения. */
export const STATUS_ACTIONS: Record<VacancyStatus, { label: string; icon: typeof Play; confirm: string }> = {
  published: { label: 'Опубликовать', icon: Send, confirm: 'Вакансия появится на карьерном сайте и начнёт принимать отклики.' },
  paused: { label: 'Приостановить', icon: Pause, confirm: 'Вакансия исчезнет с сайта; отклики и история сохранятся. Возобновить можно в любой момент.' },
  closed: { label: 'Закрыть', icon: Lock, confirm: 'Приём откликов прекратится, по старой ссылке будет «вакансия закрыта». Все отклики и история сохранятся.' },
  archived: { label: 'В архив', icon: Archive, confirm: 'Закрытая вакансия уйдёт в архив. Отклики и история сохранятся.' },
  draft: { label: 'В черновик', icon: PencilLine, confirm: '' },
}

export function useVacancyStatusAction() {
  const change = useVacancyStatus()
  const { showToast } = useToast()
  const [pending, setPending] = useState<{ vacancy: Vacancy; status: VacancyStatus } | null>(null)
  const run = async () => {
    if (!pending) return
    try {
      await change.mutateAsync({ id: pending.vacancy.id, status: pending.status })
      showToast(`Вакансия: ${pending.vacancy.allowed_statuses.find((s) => s.value === pending.status)?.label.toLowerCase() ?? 'статус изменён'}`, 'success')
    } catch (err) {
      showToast(extractErrorMessage(err), 'error')
    } finally {
      setPending(null)
    }
  }
  const label = (vacancy: Vacancy, status: VacancyStatus) =>
    status === 'published' && vacancy.status === 'paused' ? 'Возобновить' : status === 'published' && vacancy.status === 'closed' ? 'Открыть снова'
      : status === 'closed' && vacancy.status === 'archived' ? 'Вернуть из архива' : STATUS_ACTIONS[status].label
  const dialog = (
    <ConfirmDialog
      isOpen={pending !== null}
      title={pending ? `${label(pending.vacancy, pending.status)}: «${pending.vacancy.title}»?` : ''}
      message={pending ? STATUS_ACTIONS[pending.status].confirm : ''}
      confirmLabel={pending ? label(pending.vacancy, pending.status) : ''}
      tone={pending?.status === 'closed' ? 'danger' : 'primary'}
      isLoading={change.isPending}
      onConfirm={() => void run()}
      onCancel={() => setPending(null)}
    />
  )
  return { ask: (vacancy: Vacancy, status: VacancyStatus) => setPending({ vacancy, status }), label, dialog }
}

/** /hr/vacancies — вакансии: черновики, опубликованные, на паузе, закрытые и архив. */
export function HrVacanciesPage() {
  const meta = useRecruitmentMeta()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [responsible, setResponsible] = useState('')
  const [ordering, setOrdering] = useState('-created_at')
  const [page, setPage] = useState(1)
  const list = useVacancies({ search: search.trim() || undefined, status: status || undefined, responsible: responsible || undefined, ordering, page })
  const action = useVacancyStatusAction()

  return (
    <div className="space-y-5">
      <PageHeader
        title="Вакансии"
        description="Карьерный сайт показывает только опубликованные вакансии"
        actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => navigate('/hr/vacancies/new')}>Новая вакансия</Button>}
      />
      <Card>
        <div className="grid gap-3 sm:grid-cols-3">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Название, направление, город" aria-label="Поиск вакансии" />
          <Select aria-label="Статус вакансии" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} placeholder="Все статусы" options={meta.data?.vacancy_statuses ?? []} />
          <Select aria-label="Ответственный" value={responsible} onChange={(e) => { setResponsible(e.target.value); setPage(1) }} placeholder="Все ответственные"
            options={(meta.data?.people ?? []).map((p) => ({ value: String(p.id), label: p.full_name }))} />
        </div>
      </Card>
      {list.isPending ? (
        <LoadingState />
      ) : list.isError ? (
        <ErrorState message={extractErrorMessage(list.error)} onRetry={() => void list.refetch()} />
      ) : list.data.results.length === 0 ? (
        <EmptyState icon={Briefcase} title="Вакансий нет" description="Создайте вакансию: она сохранится черновиком, пока вы её не опубликуете." />
      ) : (
        <Card padding="none" className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-sm">
            <thead className={TABLE_HEAD}>
              <tr>
                <SortableTh label="Вакансия" field="title" ordering={ordering} onChange={setOrdering} />
                <Th>Статус</Th>
                <SortableTh label="Опубликована" field="published_at" ordering={ordering} onChange={setOrdering} />
                <SortableTh label="Отклики" field="applications_count" ordering={ordering} onChange={setOrdering} />
                <Th>Ответственный</Th>
                <SortableTh label="Создана" field="created_at" ordering={ordering} onChange={setOrdering} />
                <Th className="px-4 py-3 text-right">Действия</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.data.results.map((vacancy) => {
                const items: MenuItem[] = vacancy.allowed_statuses.map((s) => {
                  const Icon = STATUS_ACTIONS[s.value].icon
                  return { key: s.value, label: action.label(vacancy, s.value), icon: <Icon className="size-4" aria-hidden />,
                    tone: s.value === 'closed' ? 'danger' : 'default', onClick: () => action.ask(vacancy, s.value) }
                })
                return (
                  <tr key={vacancy.id}>
                    <td className="px-4 py-3">
                      <Link to={`/hr/vacancies/${vacancy.id}`} className="font-medium text-ink hover:text-brand-700">{vacancy.title}</Link>
                      <p className="text-xs text-ink-secondary">{[vacancy.department, vacancy.location, vacancy.work_format_label].filter(Boolean).join(' · ')}</p>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={VACANCY_TONE[vacancy.status]}>{vacancy.status_label}</Badge>
                      {vacancy.status === 'published' && !vacancy.is_accepting ? <p className="mt-1 text-xs text-warning">Срок приёма истёк</p> : null}
                      {vacancy.closes_on ? <p className="mt-1 text-xs text-ink-muted">до {formatDateShort(vacancy.closes_on)}</p> : null}
                    </td>
                    <td className="px-4 py-3 tabular-nums">{vacancy.published_at ? formatDateShort(officeDate(vacancy.published_at)) : '—'}</td>
                    <td className="px-4 py-3 tabular-nums">
                      {vacancy.applications_count ? (
                        <Link className="text-brand-700 hover:underline" to={`/hr/candidates?vacancy=${vacancy.id}`}>{vacancy.applications_count}</Link>
                      ) : 0}
                      {vacancy.new_count ? <Badge tone="info" className="ml-2">новых {vacancy.new_count}</Badge> : null}
                    </td>
                    <td className="px-4 py-3">{vacancy.responsible_info?.full_name ?? '—'}</td>
                    <td className="px-4 py-3 tabular-nums">{formatDateShort(officeDate(vacancy.created_at))}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {vacancy.status === 'published' ? (
                          <a href={`/careers/vacancies/${vacancy.slug}`} target="_blank" rel="noreferrer" aria-label={`Открыть «${vacancy.title}» на сайте`}
                            className="flex size-8 items-center justify-center rounded-lg text-ink-muted hover:bg-surface-hover hover:text-brand-700">
                            <ExternalLink className="size-4" aria-hidden />
                          </a>
                        ) : null}
                        <Button size="sm" variant="ghost" aria-label={`Изменить ${vacancy.title}`} leftIcon={<PencilLine className="size-4" aria-hidden />} onClick={() => navigate(`/hr/vacancies/${vacancy.id}`)}>Изменить</Button>
                        {items.length ? <Menu items={items} label={`Статус «${vacancy.title}»`} /> : null}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}
      {list.data ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={list.data.count} onPageChange={setPage} /> : null}
      {action.dialog}
    </div>
  )
}

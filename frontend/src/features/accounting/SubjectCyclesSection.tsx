import { Fragment, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, TriangleAlert } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { Tabs } from '@/components/ui/Tabs'
import { useCourseCycles } from '@/hooks/useAccounting'
import type { AccountingOptions, CourseCycle, CycleAccrualStatus } from '@/types/accounting'

import { Section, formatDate, som } from './shared'

type CycleTab = 'IN_PROGRESS' | 'COMPLETED' | 'INVALIDATED'

const EMPTY: Record<CycleTab, string> = {
  IN_PROGRESS: 'Незавершённых циклов предметов нет',
  COMPLETED: 'Завершённых циклов предметов нет',
  INVALIDATED: 'Отменённых циклов предметов нет',
}

const STATUS_LABEL: Record<CycleTab, string> = {
  IN_PROGRESS: 'В процессе',
  COMPLETED: 'Завершён',
  INVALIDATED: 'Отменён',
}

const ACCRUAL_TONE: Record<CycleAccrualStatus, 'info' | 'success' | 'muted' | 'warning' | 'danger'> = {
  ACCRUED: 'info',
  APPROVED: 'success',
  CANCELLED: 'muted',
  CORRECTED: 'warning',
  CORRECTION_REQUIRED: 'danger',
  REVIEW_REQUIRED: 'warning',
}

const PAGE_SIZE = 60

interface Filters {
  search: string
  course?: number
  group?: number
  subject?: number
  trainer?: number
}

/** Прогресс одного предмета: полоса + «10 / 12» (без сводного прогресса группы). */
export function SubjectProgress({ cycle }: { cycle: CourseCycle }) {
  return (
    <div className="min-w-32">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="tabular-nums font-medium text-ink">{cycle.lessons_done} / {cycle.required_lessons}</span>
        <span className="text-xs text-ink-muted">{cycle.progress_percent}%</span>
      </div>
      <div
        role="progressbar"
        aria-label={`${cycle.subject_name}: проведено ${cycle.lessons_done} из ${cycle.required_lessons}`}
        aria-valuemin={0}
        aria-valuemax={cycle.required_lessons}
        aria-valuenow={cycle.lessons_done}
        className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-hover"
      >
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${cycle.progress_percent}%` }} />
      </div>
    </div>
  )
}

function trainersText(c: CourseCycle): string {
  if (c.trainer_lessons.length) return c.trainer_lessons.map((t) => `${t.name} (${t.lessons})`).join(', ')
  return c.trainers.join(', ') || '—'
}

/**
 * Циклы по предметам: у каждой группы — отдельная строка на предмет (IT,
 * English, Soft Skills…) со своим номером цикла, прогрессом, тренерами по
 * фактическим урокам и начислениями. Общий прогресс группы не показывается:
 * он скрывал бы реальный прогресс предметов.
 */
export function SubjectCyclesSection({ options }: { options: AccountingOptions | undefined }) {
  const [tab, setTab] = useState<CycleTab>('IN_PROGRESS')
  const [filters, setFilters] = useState<Filters>({ search: '' })
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<Set<number>>(new Set())
  const cycles = useCourseCycles({
    status: tab, page, page_size: PAGE_SIZE, search: filters.search || undefined, course: filters.course,
    group: filters.group, subject: filters.subject, trainer: filters.trainer,
  })
  const change = (patch: Partial<Filters>) => { setFilters({ ...filters, ...patch }); setPage(1) }

  const groups = useMemo(() => {
    const byGroup = new Map<number, { name: string; course: string; rows: CourseCycle[] }>()
    for (const c of cycles.data?.results ?? []) {
      const entry = byGroup.get(c.group) ?? { name: c.group_name, course: c.course_name, rows: [] }
      entry.rows.push(c)
      byGroup.set(c.group, entry)
    }
    return [...byGroup.entries()]
  }, [cycles.data])

  const toggle = (id: number) => {
    const next = new Set(open)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setOpen(next)
  }

  return (
    <Section title="Циклы по предметам">
      <p className="mb-3 text-sm text-ink-secondary">
        Уроки, циклы и начисления считаются отдельно для каждого предмета группы: урок IT не меняет прогресс English
        и Soft Skills. Если цикл предмета вели несколько тренеров, каждый получает долю по своим проведённым урокам.
      </p>
      <Tabs
        aria-label="Статус циклов"
        items={[
          { key: 'IN_PROGRESS', label: 'Незавершённые' },
          { key: 'COMPLETED', label: 'Завершённые' },
          { key: 'INVALIDATED', label: 'Отменённые' },
        ] as const}
        value={tab}
        onChange={(next) => { setTab(next); setPage(1) }}
      />
      <div className="mt-4">
        <FilterBar>
          <FilterField size="lg">
            <SearchInput value={filters.search} placeholder="Поиск по названию группы" onChange={(value: string) => change({ search: value })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Курс" value={filters.course ? String(filters.course) : ''} placeholder="Все курсы"
              options={(options?.courses ?? []).map((c) => ({ value: String(c.id), label: c.name }))}
              onChange={(e) => change({ course: Number(e.target.value) || undefined, group: undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Группа" value={filters.group ? String(filters.group) : ''} placeholder="Все группы"
              options={(options?.groups ?? []).filter((g) => !filters.course || g.course === filters.course)
                .map((g) => ({ value: String(g.id), label: g.name }))}
              onChange={(e) => change({ group: Number(e.target.value) || undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Предмет" value={filters.subject ? String(filters.subject) : ''} placeholder="Все предметы"
              options={(options?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))}
              onChange={(e) => change({ subject: Number(e.target.value) || undefined })} />
          </FilterField>
          <FilterField>
            <Select aria-label="Тренер" value={filters.trainer ? String(filters.trainer) : ''} placeholder="Все тренеры"
              options={(options?.trainers ?? []).map((t) => ({ value: String(t.id), label: t.name }))}
              onChange={(e) => change({ trainer: Number(e.target.value) || undefined })} />
          </FilterField>
        </FilterBar>

        {cycles.isLoading ? <LoadingState /> : cycles.isError ? <ErrorState onRetry={() => cycles.refetch()} /> :
          groups.length === 0 ? <EmptyState title={EMPTY[tab]} description="Измените фильтры или вкладку." /> : (
            <div className="card overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Группа / предмет</th><th>Цикл</th><th>Прогресс</th><th>Тренеры (уроки)</th>
                    {tab === 'IN_PROGRESS' ? <th>Начат</th> : <th>Завершён</th>}
                    <th>Статус</th><th>Начисления</th>
                  </tr>
                </thead>
                <tbody>
                  {groups.map(([groupId, g]) => {
                    const expanded = open.has(groupId)
                    return (
                      <Fragment key={groupId}>
                        <tr className="bg-surface-muted">
                          <td colSpan={7}>
                            <button type="button" className="flex items-center gap-1.5 font-semibold text-ink" aria-expanded={expanded}
                              onClick={() => toggle(groupId)}>
                              {expanded ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
                              {g.name}
                              <span className="text-xs font-normal text-ink-muted">· {g.course} · предметов: {g.rows.length}</span>
                            </button>
                          </td>
                        </tr>
                        {g.rows.map((c) => (
                          <Fragment key={c.id}>
                            <tr>
                              <td className="pl-8">
                                <span className="font-medium text-ink">{c.subject_name}</span>
                                {c.subject_plan_lessons ? (
                                  <p className="text-xs text-ink-muted">всего по предмету: {c.lessons_total} / {c.subject_plan_lessons} по плану</p>
                                ) : null}
                              </td>
                              <td>№{c.number}</td>
                              <td><SubjectProgress cycle={c} /></td>
                              <td className="text-sm">{trainersText(c)}</td>
                              <td className="whitespace-nowrap">{formatDate(tab === 'IN_PROGRESS' ? c.start_date : c.completed_on)}</td>
                              <td><Badge tone={tab === 'COMPLETED' ? 'success' : tab === 'INVALIDATED' ? 'muted' : 'info'}>{STATUS_LABEL[tab]}</Badge></td>
                              <td className="text-sm">
                                {c.accruals.length === 0 ? <span className="text-ink-muted">{tab === 'IN_PROGRESS' ? 'после завершения' : '—'}</span>
                                  : c.accruals.map((a) => (
                                    <p key={a.id} className="whitespace-nowrap">
                                      {a.employee_name}: {som(a.amount)} <Badge tone={ACCRUAL_TONE[a.status]}>{a.status_display}</Badge>
                                    </p>
                                  ))}
                                {c.warnings.map((w) => (
                                  <p key={w} className="mt-1 flex gap-1 text-xs text-warning"><TriangleAlert className="size-3.5 shrink-0" aria-hidden />{w}</p>
                                ))}
                              </td>
                            </tr>
                            {expanded ? <CycleDetails cycle={c} /> : null}
                          </Fragment>
                        ))}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        {cycles.data ? (
          <div className="mt-4">
            <Pagination page={page} pageSize={PAGE_SIZE} totalCount={cycles.data.count} onPageChange={setPage} />
          </div>
        ) : null}
      </div>
    </Section>
  )
}

function CycleDetails({ cycle: c }: { cycle: CourseCycle }) {
  return (
    <tr>
      <td colSpan={7} className="bg-surface-muted/50 pl-8 text-sm">
        <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-4">
          <div><dt className="text-xs text-ink-muted">Предмет</dt><dd>{c.subject_name}</dd></div>
          <div><dt className="text-xs text-ink-muted">Осталось уроков</dt><dd>{c.lessons_remaining}</dd></div>
          {c.status === 'IN_PROGRESS' ? (
            <div className="sm:col-span-2"><dt className="text-xs text-ink-muted">Студенты и база</dt>
              <dd className="text-ink-secondary">фиксируются на дату завершения цикла</dd></div>
          ) : (
            <>
              <div><dt className="text-xs text-ink-muted">Студенты</dt><dd>{c.student_count ?? '—'}</dd></div>
              <div><dt className="text-xs text-ink-muted">База (студенты × тариф)</dt><dd>{c.base_amount ? som(c.base_amount) : '—'}</dd></div>
            </>
          )}
        </dl>
        {c.trainer_lessons.length ? (
          <p className="mt-2 text-xs text-ink-secondary">
            Уроки по тренерам: {c.trainer_lessons.map((t) => `${t.name} — ${t.lessons} из ${c.required_lessons}`).join('; ')}
          </p>
        ) : null}
        {c.accruals.map((a) => (
          <p key={a.id} className="mt-1 text-xs text-ink-secondary">
            {a.employee_name}: {Number(a.percentage)}%{a.lessons_taught !== null ? ` × ${a.lessons_taught}/${c.required_lessons} ур.` : ' (весь цикл)'} = {som(a.amount)}
            {a.period_label ? ` · ${a.period_label}, ${a.payroll_status_display}` : ' · ещё не в расчёте'} · плановая выплата {formatDate(a.planned_payment_date)}
          </p>
        ))}
        {c.invalidated_reason ? <p className="mt-1 text-xs text-warning">{c.invalidated_reason}</p> : null}
      </td>
    </tr>
  )
}

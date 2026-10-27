import { useState } from 'react'
import { Download } from 'lucide-react'
import { Link } from 'react-router-dom'

import { recruitmentApi } from '@/api/hr'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { Tabs } from '@/components/ui/Tabs'
import { useToast } from '@/components/ui/Toast'
import { useAllVacancies, useDailyReport, useMonthlyReport, useRecruitmentMeta } from '@/hooks/useHr'
import { extractErrorMessage } from '@/lib/apiError'
import type { DailyReport, MonthlyReport, ReportFilters } from '@/types/hr'
import { formatRuPercent } from '@/utils/format'

import { CandidateStatusBadge, INTERVIEW_TONE, officeTime, TABLE_HEAD, Th } from './shared'

type Period = 'daily' | 'monthly'

/** /hr/reports — ежедневный и ежемесячный кадровые отчёты по данным базы,
 * фильтры по должности, вакансии, источнику и ответственному, экспорт в CSV. */
export function HrReportsPage() {
  const meta = useRecruitmentMeta()
  const vacancies = useAllVacancies()
  const { showToast } = useToast()
  const [period, setPeriod] = useState<Period>('daily')
  const [date, setDate] = useState('')
  const [month, setMonth] = useState('')
  const [filters, setFilters] = useState<ReportFilters>({})
  const [exporting, setExporting] = useState(false)
  const clean = Object.fromEntries(Object.entries(filters).filter(([, v]) => v)) as ReportFilters
  const dayParams = { ...clean, date: date || meta.data?.today }
  const monthParams = { ...clean, month: month || meta.data?.today.slice(0, 7) }
  const daily = useDailyReport(dayParams)
  const monthly = useMonthlyReport(monthParams)
  const set = (key: keyof ReportFilters) => (value: string) => setFilters((f) => ({ ...f, [key]: value || undefined }))

  const exportCsv = async () => {
    setExporting(true)
    try {
      if (period === 'daily') await recruitmentApi.exportDaily(dayParams)
      else await recruitmentApi.exportMonthly(monthParams)
    } catch (err) {
      showToast(extractErrorMessage(err), 'error')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Отчёты"
        description="Подбор персонала за день и за месяц"
        actions={<Button variant="secondary" leftIcon={<Download className="size-4" aria-hidden />} isLoading={exporting} onClick={() => void exportCsv()}>Экспорт CSV</Button>}
      />
      <Tabs items={[{ key: 'daily', label: 'День' }, { key: 'monthly', label: 'Месяц' }] as const} value={period} onChange={setPeriod} aria-label="Период отчёта" />
      <Card>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {period === 'daily' ? (
            <label className="text-sm"><span className="mb-1 block field-label">Дата</span>
              <DatePicker aria-label="Дата отчёта" value={date || meta.data?.today || ''} onChange={(e) => setDate(e.target.value)} />
            </label>
          ) : (
            <label className="text-sm"><span className="mb-1 block field-label">Месяц</span>
              <Input aria-label="Месяц отчёта" type="month" value={month || meta.data?.today.slice(0, 7) || ''} onChange={(e) => setMonth(e.target.value)} />
            </label>
          )}
          <label className="text-sm"><span className="mb-1 block field-label">Должность</span>
            <SearchInput aria-label="Должность" value={filters.position ?? ''} onChange={set('position')} placeholder="Например, SMM" />
          </label>
          <label className="text-sm"><span className="mb-1 block field-label">Вакансия</span>
            <Select aria-label="Вакансия" value={filters.vacancy ?? ''} onChange={(e) => set('vacancy')(e.target.value)} placeholder="Все" options={(vacancies.data?.results ?? []).map((v) => ({ value: String(v.id), label: v.title }))} />
          </label>
          <label className="text-sm"><span className="mb-1 block field-label">Источник</span>
            <Select aria-label="Источник" value={filters.source ?? ''} onChange={(e) => set('source')(e.target.value)} placeholder="Все" options={meta.data?.sources ?? []} />
          </label>
          <label className="text-sm"><span className="mb-1 block field-label">Ответственный</span>
            <Select aria-label="Ответственный" value={filters.responsible ?? ''} onChange={(e) => set('responsible')(e.target.value)} placeholder="Все" options={(meta.data?.people ?? []).map((p) => ({ value: String(p.id), label: p.full_name }))} />
          </label>
        </div>
      </Card>
      {period === 'daily' ? (
        daily.isPending ? <LoadingState /> : daily.isError ? <ErrorState message={extractErrorMessage(daily.error)} onRetry={() => void daily.refetch()} /> : <Daily report={daily.data} />
      ) : monthly.isPending ? <LoadingState /> : monthly.isError ? <ErrorState message={extractErrorMessage(monthly.error)} onRetry={() => void monthly.refetch()} /> : <Monthly report={monthly.data} />}
    </div>
  )
}

function Daily({ report: r }: { report: DailyReport }) {
  return (
    <div className="space-y-5">
      <StatGrid columns={4}>
        <StatCard label="Новые кандидаты" value={r.new_candidates} />
        <StatCard label="Запланировано собеседований" value={r.interviews_planned} />
        <StatCard label="Проведено" value={r.interviews_conducted} />
        <StatCard label="Перенесено / отменено" value={`${r.interviews_rescheduled} / ${r.interviews_cancelled}`} />
        <StatCard label="Ожидают решения (сейчас)" value={r.awaiting_decision_now} tone={r.awaiting_decision_now ? 'warning' : 'default'} />
        <StatCard label="Принятые решения" value={r.decisions} hint={`Предложений: ${r.offers}`} />
        <StatCard label="Приняты на работу" value={r.hired} />
        <StatCard label="Отказы" value={r.rejected} hint={r.withdrawn ? `Кандидат отказался: ${r.withdrawn}` : undefined} />
      </StatGrid>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Собеседования дня" padding="none">
          {r.interviews_list.length === 0 ? <p className="px-5 py-4 text-sm text-ink-secondary">Собеседований нет.</p> : (
            <ul className="divide-y divide-border">
              {r.interviews_list.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-2.5">
                  <span className="min-w-0 text-sm">
                    <span className="font-medium tabular-nums">{officeTime(i.scheduled_at)}</span>{' '}
                    <Link className="text-brand-700 hover:underline" to={`/hr/candidates/${i.candidate.id}`}>{i.candidate.full_name}</Link>
                    <span className="block text-xs text-ink-secondary">{i.position || '—'} · {i.interviewer}</span>
                  </span>
                  <Badge tone={INTERVIEW_TONE[i.status]}>{i.status_label}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Новые кандидаты" padding="none">
          {r.new_candidates_list.length === 0 ? <p className="px-5 py-4 text-sm text-ink-secondary">Новых кандидатов нет.</p> : (
            <ul className="divide-y divide-border">
              {r.new_candidates_list.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-2.5">
                  <span className="min-w-0 text-sm">
                    <Link className="font-medium text-brand-700 hover:underline" to={`/hr/candidates/${c.id}`}>{c.full_name}</Link>
                    <span className="block text-xs text-ink-secondary">{c.position || '—'} · {c.source_label}</span>
                  </span>
                  <CandidateStatusBadge status={c.status} label={c.status_label} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}

function CountTable({ title, rows, label }: { title: string; rows: { label: string; count: number }[]; label: string }) {
  return (
    <Card title={title} padding="none">
      {rows.length === 0 ? <p className="px-5 py-4 text-sm text-ink-secondary">Нет данных.</p> : (
        <table className="w-full text-sm">
          <thead className={TABLE_HEAD}><tr><Th>{label}</Th><Th className="px-4 py-3 text-right">Кандидатов</Th></tr></thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => <tr key={row.label}><td className="px-4 py-2.5">{row.label}</td><td className="px-4 py-2.5 text-right tabular-nums">{row.count}</td></tr>)}
          </tbody>
        </table>
      )}
    </Card>
  )
}

function hours(value: number): string {
  if (value < 1) return '< 1 ч'
  return value >= 48 ? `${(value / 24).toFixed(1).replace('.', ',')} дн.` : `${String(value).replace('.', ',')} ч`
}

function Monthly({ report: r }: { report: MonthlyReport }) {
  return (
    <div className="space-y-5">
      <StatGrid columns={4}>
        <StatCard label="Новые кандидаты" value={r.new_candidates} />
        <StatCard label="Проведено собеседований" value={r.interviews_conducted} />
        <StatCard label="Отменено / переносов" value={`${r.interviews_cancelled} / ${r.interviews_rescheduled}`} />
        <StatCard label="Приняты на работу" value={r.hired} hint={r.average_days_to_hire !== null ? `В среднем за ${String(r.average_days_to_hire).replace('.', ',')} дн.` : undefined} />
        <StatCard label="Предложения о работе" value={r.offers} />
        <StatCard label="Отказы" value={r.rejected} />
        <StatCard label="Кандидат отказался" value={r.withdrawn} />
      </StatGrid>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Воронка кандидатов месяца" description="Сколько кандидатов, добавленных в этом месяце, дошли до этапа или дальше; конверсия — от предыдущего этапа" padding="none">
          <table className="w-full text-sm">
            <thead className={TABLE_HEAD}><tr><Th>Этап</Th><Th className="px-4 py-3 text-right">Дошли</Th><Th className="px-4 py-3 text-right">Конверсия</Th></tr></thead>
            <tbody className="divide-y divide-border">
              {r.funnel.map((row) => (
                <tr key={row.status}>
                  <td className="px-4 py-2.5">{row.status_label}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{row.count}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{formatRuPercent(row.conversion_percent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Кандидаты месяца по этапам" padding="none">
          <table className="w-full text-sm">
            <thead className={TABLE_HEAD}><tr><Th>Текущий этап</Th><Th className="px-4 py-3 text-right">Кандидатов</Th></tr></thead>
            <tbody className="divide-y divide-border">
              {r.by_stage.map((row) => <tr key={row.status}><td className="px-4 py-2.5">{row.status_label}</td><td className="px-4 py-2.5 text-right tabular-nums">{row.count}</td></tr>)}
            </tbody>
          </table>
        </Card>
        <CountTable title="По вакансиям" rows={r.by_vacancy} label="Вакансия" />
        <CountTable title="По источникам" rows={r.by_source} label="Источник" />
        <Card title="Среднее время на этапе" description="По переходам, завершившимся в этом месяце; время входа в этап взято из журнала" padding="none">
          {r.stage_durations.length === 0 ? <p className="px-5 py-4 text-sm text-ink-secondary">Недостаточно истории переходов за месяц.</p> : (
            <table className="w-full text-sm">
              <thead className={TABLE_HEAD}><tr><Th>Этап</Th><Th className="px-4 py-3 text-right">Переходов</Th><Th className="px-4 py-3 text-right">В среднем</Th></tr></thead>
              <tbody className="divide-y divide-border">
                {r.stage_durations.map((row) => (
                  <tr key={row.status}>
                    <td className="px-4 py-2.5">{row.status_label}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{row.transitions}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{hours(row.average_hours)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  )
}

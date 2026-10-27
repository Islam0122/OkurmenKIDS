import { useState } from 'react'
import { Download, Info } from 'lucide-react'
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
import type { DailyReport, PeriodParams, PeriodReport, ReportDefinitions, ReportFilters } from '@/types/hr'
import { formatRuPercent } from '@/utils/format'

import { ApplicationStatusBadge, INTERVIEW_TONE, TABLE_HEAD, Th, candidatePath, officeTime } from './shared'

type Period = 'daily' | 'monthly' | 'custom'

const num = (value: number) => String(value).replace('.', ',')

/** /hr/reports — ежедневный, месячный и отчёт за произвольный период по данным
 * базы; фильтры по вакансии, ответственному HR, источнику и должности; CSV. */
export function HrReportsPage() {
  const meta = useRecruitmentMeta()
  const vacancies = useAllVacancies()
  const { showToast } = useToast()
  const [period, setPeriod] = useState<Period>('daily')
  const [date, setDate] = useState('')
  const [month, setMonth] = useState('')
  const [range, setRange] = useState({ date_from: '', date_to: '' })
  const [filters, setFilters] = useState<ReportFilters>({})
  const [exporting, setExporting] = useState(false)
  const clean = Object.fromEntries(Object.entries(filters).filter(([, v]) => v)) as ReportFilters
  const today = meta.data?.today
  const dayParams = { ...clean, date: date || today }
  const periodParams: PeriodParams = period === 'custom'
    ? { ...clean, date_from: range.date_from || (today ? `${today.slice(0, 8)}01` : undefined), date_to: range.date_to || today }
    : { ...clean, month: month || today?.slice(0, 7) }
  const daily = useDailyReport(dayParams)
  const monthly = useMonthlyReport(periodParams)
  const set = (key: keyof ReportFilters) => (value: string) => setFilters((f) => ({ ...f, [key]: value || undefined }))

  const exportCsv = async () => {
    setExporting(true)
    try {
      if (period === 'daily') await recruitmentApi.exportDaily(dayParams)
      else await recruitmentApi.exportMonthly(periodParams)
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
        description="Подбор персонала за день, месяц или выбранный период — по данным системы"
        actions={<Button variant="secondary" leftIcon={<Download className="size-4" aria-hidden />} isLoading={exporting} onClick={() => void exportCsv()}>Экспорт CSV</Button>}
      />
      <Tabs items={[{ key: 'daily', label: 'День' }, { key: 'monthly', label: 'Месяц' }, { key: 'custom', label: 'Период' }] as const} value={period} onChange={setPeriod} aria-label="Период отчёта" />
      <Card>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {period === 'daily' ? (
            <label className="text-sm"><span className="mb-1 block field-label">Дата</span>
              <DatePicker aria-label="Дата отчёта" value={date || today || ''} onChange={(e) => setDate(e.target.value)} />
            </label>
          ) : period === 'monthly' ? (
            <label className="text-sm"><span className="mb-1 block field-label">Месяц</span>
              <Input aria-label="Месяц отчёта" type="month" value={month || today?.slice(0, 7) || ''} onChange={(e) => setMonth(e.target.value)} />
            </label>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <label className="text-sm"><span className="mb-1 block field-label">С</span>
                <DatePicker aria-label="Начало периода" value={periodParams.date_from ?? ''} onChange={(e) => setRange((r) => ({ ...r, date_from: e.target.value }))} />
              </label>
              <label className="text-sm"><span className="mb-1 block field-label">По</span>
                <DatePicker aria-label="Конец периода" value={periodParams.date_to ?? ''} onChange={(e) => setRange((r) => ({ ...r, date_to: e.target.value }))} />
              </label>
            </div>
          )}
          <label className="text-sm"><span className="mb-1 block field-label">Вакансия</span>
            <Select aria-label="Вакансия" value={filters.vacancy ?? ''} onChange={(e) => set('vacancy')(e.target.value)} placeholder="Все" options={(vacancies.data?.results ?? []).map((v) => ({ value: String(v.id), label: v.title }))} />
          </label>
          <label className="text-sm"><span className="mb-1 block field-label">Ответственный HR</span>
            <Select aria-label="Ответственный" value={filters.responsible ?? ''} onChange={(e) => set('responsible')(e.target.value)} placeholder="Все" options={(meta.data?.people ?? []).map((p) => ({ value: String(p.id), label: p.full_name }))} />
          </label>
          <label className="text-sm"><span className="mb-1 block field-label">Источник</span>
            <Select aria-label="Источник" value={filters.source ?? ''} onChange={(e) => set('source')(e.target.value)} placeholder="Все" options={meta.data?.sources ?? []} />
          </label>
          <label className="text-sm"><span className="mb-1 block field-label">Должность</span>
            <SearchInput aria-label="Должность" value={filters.position ?? ''} onChange={set('position')} placeholder="Например, SMM" />
          </label>
        </div>
      </Card>
      {period === 'daily' ? (
        daily.isPending ? <LoadingState /> : daily.isError ? <ErrorState message={extractErrorMessage(daily.error)} onRetry={() => void daily.refetch()} /> : <Daily report={daily.data} />
      ) : monthly.isPending ? <LoadingState /> : monthly.isError ? <ErrorState message={extractErrorMessage(monthly.error)} onRetry={() => void monthly.refetch()} /> : <Monthly report={monthly.data} />}
    </div>
  )
}

function Definitions({ definitions }: { definitions: ReportDefinitions }) {
  return (
    <details className="card card-body text-sm">
      <summary className="flex cursor-pointer items-center gap-2 font-medium text-ink"><Info className="size-4 text-info" aria-hidden />Как считаются показатели</summary>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-ink-secondary">
        {Object.entries(definitions).map(([key, text]) => <li key={key}>{text}</li>)}
      </ul>
    </details>
  )
}

function CountList({ title, rows, label, empty }: { title: string; rows: { label: string; count: number }[]; label: string; empty: string }) {
  return (
    <Card title={title} padding="none">
      {rows.length === 0 ? <p className="px-5 py-4 text-sm text-ink-secondary">{empty}</p> : (
        <table className="w-full text-sm">
          <thead className={TABLE_HEAD}><tr><Th>{label}</Th><Th className="px-4 py-3 text-right">Откликов</Th></tr></thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => <tr key={row.label}><td className="px-4 py-2.5">{row.label}</td><td className="px-4 py-2.5 text-right tabular-nums">{row.count}</td></tr>)}
          </tbody>
        </table>
      )}
    </Card>
  )
}

function Daily({ report: r }: { report: DailyReport }) {
  return (
    <div className="space-y-5">
      <StatGrid columns={4}>
        <StatCard label="Новые отклики" value={r.new_applications} />
        <StatCard label="Прошли первичный отбор" value={r.passed_screening} />
        <StatCard label="Назначено собеседований" value={r.interviews_scheduled} hint={`Запланировано на этот день: ${r.interviews_planned}`} />
        <StatCard label="Проведено собеседований" value={r.interviews_conducted} />
        <StatCard label="Перенесено / отменено" value={`${r.interviews_rescheduled} / ${r.interviews_cancelled}`} hint={r.interviews_no_show ? `Не пришли: ${r.interviews_no_show}` : undefined} />
        <StatCard label="Принятые решения" value={r.decisions} hint={`Ожидают решения сейчас: ${r.awaiting_decision_now}`} />
        <StatCard label="Предложения о работе" value={r.offers} />
        <StatCard label="Приняты / отказ" value={`${r.hired} / ${r.rejected}`} hint={r.withdrawn ? `Кандидат отказался: ${r.withdrawn}` : undefined} />
      </StatGrid>
      <div className="grid gap-5 lg:grid-cols-2">
        <CountList title="Отклики по вакансиям" rows={r.new_by_vacancy} label="Вакансия" empty="Откликов в этот день не было." />
        <Card title="Собеседования дня" padding="none">
          {r.interviews_list.length === 0 ? <p className="px-5 py-4 text-sm text-ink-secondary">Собеседований нет.</p> : (
            <ul className="divide-y divide-border">
              {r.interviews_list.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-2.5">
                  <span className="min-w-0 text-sm">
                    <span className="font-medium tabular-nums">{officeTime(i.scheduled_at)}</span>{' '}
                    <Link className="text-brand-700 hover:underline" to={candidatePath(i.candidate.id, i.application)}>{i.candidate.full_name}</Link>
                    <span className="block text-xs text-ink-secondary">{i.position || '—'} · {i.interviewer}</span>
                  </span>
                  <Badge tone={INTERVIEW_TONE[i.status]}>{i.status_label}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Новые отклики" padding="none" className="lg:col-span-2">
          {r.new_applications_list.length === 0 ? <p className="px-5 py-4 text-sm text-ink-secondary">Новых откликов нет.</p> : (
            <ul className="divide-y divide-border">
              {r.new_applications_list.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-2.5">
                  <span className="min-w-0 text-sm">
                    <Link className="font-medium text-brand-700 hover:underline" to={candidatePath(a.candidate.id, a.id)}>{a.candidate.full_name}</Link>
                    <span className="block text-xs text-ink-secondary">{a.position || '—'} · {a.source_label} · {a.number}</span>
                  </span>
                  <ApplicationStatusBadge status={a.status} label={a.status_label} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <Definitions definitions={r.definitions} />
    </div>
  )
}

function hours(value: number): string {
  if (value < 1) return '< 1 ч'
  return value >= 48 ? `${num(Number((value / 24).toFixed(1)))} дн.` : `${num(value)} ч`
}

function Monthly({ report: r }: { report: PeriodReport }) {
  return (
    <div className="space-y-5">
      <StatGrid columns={4}>
        <StatCard label="Новые отклики" value={r.new_applications} hint={`Прошли первичный отбор: ${r.passed_screening}`} />
        <StatCard label="Проведено собеседований" value={r.interviews_conducted} hint={`Назначено: ${r.interviews_scheduled}`} />
        <StatCard label="Отменено / переносов" value={`${r.interviews_cancelled} / ${r.interviews_rescheduled}`} hint={r.interviews_no_show ? `Не пришли: ${r.interviews_no_show}` : undefined} />
        <StatCard label="Предложения о работе" value={r.offers} />
        <StatCard label="Приняты на работу" value={r.hired} hint={r.average_days_to_hire !== null ? `В среднем за ${num(r.average_days_to_hire)} дн. от отклика` : 'Нет данных о сроке найма'} />
        <StatCard label="Отказ компании" value={r.rejected} />
        <StatCard label="Кандидат отказался" value={r.withdrawn} />
        <StatCard label="Закрыто вакансий" value={r.vacancies_closed}
          hint={r.vacancy_days_to_close !== null ? `В среднем ${num(r.vacancy_days_to_close)} дн. от публикации` : 'Нет вакансий с обеими датами'} />
      </StatGrid>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Воронка и конверсия" description="Отклики периода: сколько дошли до этапа или дальше; конверсия — от предыдущего этапа" padding="none">
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
        <Card title="Отклики периода по текущим этапам" padding="none">
          <table className="w-full text-sm">
            <thead className={TABLE_HEAD}><tr><Th>Этап</Th><Th className="px-4 py-3 text-right">Откликов</Th></tr></thead>
            <tbody className="divide-y divide-border">
              {r.by_stage.map((row) => <tr key={row.status}><td className="px-4 py-2.5">{row.status_label}</td><td className="px-4 py-2.5 text-right tabular-nums">{row.count}</td></tr>)}
            </tbody>
          </table>
        </Card>
        <Card title="По вакансиям" padding="none" className="overflow-x-auto lg:col-span-2">
          {r.by_vacancy.length === 0 ? <p className="px-5 py-4 text-sm text-ink-secondary">Нет данных за период.</p> : (
            <table className="w-full min-w-[560px] text-sm">
              <thead className={TABLE_HEAD}><tr><Th>Вакансия</Th><Th className="px-4 py-3 text-right">Откликов</Th><Th className="px-4 py-3 text-right">Собеседований</Th><Th className="px-4 py-3 text-right">Предложений</Th><Th className="px-4 py-3 text-right">Принято</Th><Th className="px-4 py-3 text-right">Отказов</Th></tr></thead>
              <tbody className="divide-y divide-border">
                {r.by_vacancy.map((row) => (
                  <tr key={row.label}>
                    <td className="px-4 py-2.5">{row.label}</td>
                    {[row.applications, row.interviews, row.offers, row.hired, row.rejected].map((value, i) => <td key={i} className="px-4 py-2.5 text-right tabular-nums">{value}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title="Источники кандидатов" description="Эффективность — когда из источника пришло достаточно откликов" padding="none" className="overflow-x-auto">
          {r.by_source.length === 0 ? <p className="px-5 py-4 text-sm text-ink-secondary">Нет данных за период.</p> : (
            <table className="w-full min-w-[420px] text-sm">
              <thead className={TABLE_HEAD}><tr><Th>Источник</Th><Th className="px-4 py-3 text-right">Откликов</Th><Th className="px-4 py-3 text-right">До собеседования</Th><Th className="px-4 py-3 text-right">Приняты</Th></tr></thead>
              <tbody className="divide-y divide-border">
                {r.by_source.map((row) => (
                  <tr key={row.source}>
                    <td className="px-4 py-2.5">{row.label}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{row.count}</td>
                    {row.enough_data ? (
                      <>
                        <td className="px-4 py-2.5 text-right tabular-nums">{formatRuPercent(row.interview_percent)}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{formatRuPercent(row.hired_percent)}</td>
                      </>
                    ) : <td colSpan={2} className="px-4 py-2.5 text-right text-xs text-ink-muted">мало данных</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title="Среднее время на этапе" description="По переходам, завершившимся в периоде" padding="none">
          {r.stage_durations.length === 0 ? <p className="px-5 py-4 text-sm text-ink-secondary">Недостаточно истории переходов за период.</p> : (
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
      <Definitions definitions={r.definitions} />
    </div>
  )
}

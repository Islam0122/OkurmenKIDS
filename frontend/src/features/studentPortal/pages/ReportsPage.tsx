import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Download, Info } from 'lucide-react'

import { studentPortalApi } from '@/api/studentPortal'
import { cn } from '@/utils/cn'

import { PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import { MonthSwitcher } from './AttendancePage'
import { FeedbackList } from './DashboardPage'
import { Bar, Columns, Empty, GroupedColumns, LoadError, Loading, PCard, PageTitle, ProgressRing, Stat, downloadBlob } from '../ui'

function Change({ value, unit = '' }: { value: number | null; unit?: string }) {
  const { t } = usePortalI18n()
  if (value === null || value === 0) return null
  return (
    <span className={cn('text-xs font-medium', value > 0 ? 'text-brand-700' : 'text-danger')}>
      {t('report.change', { sign: value > 0 ? '+' : '', n: `${value}${unit}` })}
    </span>
  )
}

const pct = (value: number | null) => (value === null ? '—' : `${Math.round(value)}%`)

export function StudentReportsPage() {
  const { student } = usePortal()
  const { t, lang, month: monthName } = usePortalI18n()
  const now = new Date()
  const [[year, month], setMonth] = useState<[number, number]>([now.getFullYear(), now.getMonth() + 1])
  const [asTable, setAsTable] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'report', student.id, year, month],
    queryFn: () => studentPortalApi.monthlyReport(student.id, year, month),
    placeholderData: keepPreviousData,
  })

  const download = async () => {
    setDownloading(true)
    try {
      const blob = await studentPortalApi.monthlyReportPdf(student.id, year, month, lang)
      downloadBlob(blob, `report_${student.last_name || student.first_name}_${year}-${String(month).padStart(2, '0')}.pdf`)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div>
      <PageTitle title={t('report.title')} subtitle={t('report.subtitle')}
        actions={
          <>
            <MonthSwitcher year={year} month={month} onChange={(y, m) => setMonth([y, m])} />
            <button type="button" onClick={() => void download()} disabled={downloading || !data}
              className="inline-flex h-10 items-center gap-2 rounded-xl bg-brand-500 px-4 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-60">
              <Download className="size-4" aria-hidden />{t('report.download')}
            </button>
          </>
        } />
      {isPending ? <Loading /> : isError || !data ? <LoadError onRetry={() => void refetch()} /> : (
        <div className="space-y-5">
          {!data.period.is_complete ? (
            <p className="flex items-center gap-2 rounded-xl bg-info-soft px-4 py-2.5 text-sm text-info"><Info className="size-4" aria-hidden />{t('report.preliminary')}</p>
          ) : null}

          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            <PCard title={t('report.attendance')}>
              <div className="flex items-center gap-4">
                <ProgressRing value={data.attendance.percent} label={t('report.attendance')} />
                <div className="space-y-0.5 text-sm text-ink-secondary">
                  <p>{t('report.totalLessons')}: <b className="text-ink">{data.attendance.total_lessons}</b></p>
                  <p>{t('report.attended')}: <b className="text-ink">{data.attendance.attended}</b></p>
                  <p>{t('report.missed')}: <b className="text-ink">{data.attendance.missed}</b></p>
                  <Change value={data.progress.change.attendance_rate} unit="%" />
                </div>
              </div>
            </PCard>
            <PCard title={t('report.homework')}>
              <p className="text-3xl font-bold tabular-nums text-ink">{pct(data.homework.completion_rate)}</p>
              <p className="mb-2 text-sm text-ink-secondary">{t('report.completion')}: {data.homework.completed} {t('common.of')} {data.homework.assigned}</p>
              <Bar value={data.homework.completion_rate} />
              <div className="mt-1"><Change value={data.progress.change.homework_rate} unit="%" /></div>
            </PCard>
            <PCard title={t('report.avgScore')}>
              <p className="text-3xl font-bold tabular-nums text-ink">{data.homework.average_score ?? '—'}<span className="text-base font-semibold text-ink-muted"> / 10</span></p>
              <p className="mb-2 text-sm text-ink-secondary">{t('report.testsAvg')}: {pct(data.tests.average)}</p>
              <Bar value={data.homework.average_score === null ? null : data.homework.average_score * 10} />
              <div className="mt-1"><Change value={data.progress.change.average_score} /></div>
            </PCard>
            <PCard title={t('report.xp')}>
              <p className="text-3xl font-bold tabular-nums text-brand-700">+{data.xp.total} <span className="text-base font-semibold">XP</span></p>
              <ul className="mt-2 space-y-0.5 text-sm text-ink-secondary">
                <li>+{data.xp.attendance} {t('report.xpAttendance')}</li>
                <li>+{data.xp.homework} {t('report.xpHomework')}</li>
                <li>+{data.xp.tests} {t('report.xpTests')}</li>
              </ul>
            </PCard>
          </div>

          <div className="grid gap-5 lg:grid-cols-3">
            <PCard title={t('report.trend')} className="lg:col-span-2"
              action={
                <button type="button" onClick={() => setAsTable((v) => !v)} className="text-sm font-medium text-brand-700">
                  {asTable ? t('common.chart') : t('common.table')}
                </button>
              }>
              {asTable ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-left text-xs text-ink-muted"><th className="py-2">{t('report.month')}</th><th>{t('report.attendance')}</th><th>{t('report.homework')}</th><th>{t('report.avgScore')}</th><th>XP</th></tr></thead>
                    <tbody className="divide-y divide-border/70">
                      {data.trend.map((row) => (
                        <tr key={`${row.year}-${row.month}`} className="tabular-nums">
                          <td className="py-2 text-ink">{monthName(row.month)} {row.year}</td>
                          <td>{pct(row.attendance_rate)}</td><td>{pct(row.homework_rate)}</td><td>{row.average_score ?? '—'}</td><td>{row.xp}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <GroupedColumns
                  series={[t('report.attendance'), t('report.homework')]}
                  points={data.trend.map((row) => ({ label: monthName(row.month).slice(0, 3), values: [row.attendance_rate, row.homework_rate] }))}
                />
              )}
            </PCard>
            <PCard title={t('report.trendXp')}>
              <Columns points={data.trend.map((row) => ({ label: monthName(row.month).slice(0, 3), value: row.xp }))} />
            </PCard>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <PCard title={t('report.progress')}>
              {data.progress.subjects.length === 0 ? <Empty>{t('common.noData')}</Empty> : (
                <ul className="space-y-4">
                  {data.progress.subjects.map((s) => (
                    <li key={s.subject}>
                      <div className="mb-1.5 flex items-baseline justify-between gap-2">
                        <span className="font-medium text-ink">{s.subject}</span>
                        <span className="text-xs text-ink-muted">{t('common.lessonsCount', { n: s.lessons })}</span>
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <Stat label={t('report.attendance')} value={pct(s.attendance_rate)} />
                        <Stat label={t('report.homework')} value={pct(s.homework_rate)} />
                        <Stat label={t('report.avgScore')} value={s.average_score ?? '—'} accent />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </PCard>
            <PCard title={t('report.tests')}>
              {data.tests.items.length === 0 ? <Empty>{t('report.noTests')}</Empty> : (
                <ul className="divide-y divide-border/70">
                  {data.tests.items.map((test) => (
                    <li key={test.id} className="flex items-center justify-between gap-3 py-2.5">
                      <span className="min-w-0 truncate text-sm text-ink">{test.title}</span>
                      <span className={cn('shrink-0 rounded-full px-2.5 py-0.5 text-sm font-semibold tabular-nums',
                        test.passed === false ? 'bg-danger-soft text-danger' : 'bg-brand-50 text-brand-700')}>{Math.round(test.score)}%</span>
                    </li>
                  ))}
                </ul>
              )}
            </PCard>
          </div>

          <PCard title={t('report.comments')}>
            {data.comments.length === 0 ? <Empty>{t('report.noComments')}</Empty> : <FeedbackList items={data.comments} />}
          </PCard>
        </div>
      )}
    </div>
  )
}

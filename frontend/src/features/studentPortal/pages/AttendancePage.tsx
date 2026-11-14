import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { studentPortalApi } from '@/api/studentPortal'

import { PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import { AttendanceBadge, Empty, LoadError, Loading, PCard, PageTitle, ProgressRing, Stat } from '../ui'

export function MonthSwitcher({ year, month, onChange }: { year: number; month: number; onChange: (y: number, m: number) => void }) {
  const { t, month: monthName } = usePortalI18n()
  const now = new Date()
  const isCurrent = year === now.getFullYear() && month === now.getMonth() + 1
  const go = (delta: number) => {
    const index = year * 12 + (month - 1) + delta
    onChange(Math.floor(index / 12), (index % 12) + 1)
  }
  return (
    <div className="flex items-center gap-1 rounded-xl bg-surface p-1 shadow-sm ring-1 ring-border/70">
      <button type="button" onClick={() => go(-1)} aria-label={t('schedule.prev')} className="rounded-lg p-1.5 text-ink-secondary hover:bg-surface-hover"><ChevronLeft className="size-5" /></button>
      <span className="min-w-32 text-center text-sm font-semibold text-ink">{monthName(month)} {year}</span>
      <button type="button" onClick={() => go(1)} disabled={isCurrent} aria-label={t('schedule.next')} className="rounded-lg p-1.5 text-ink-secondary hover:bg-surface-hover disabled:opacity-30"><ChevronRight className="size-5" /></button>
    </div>
  )
}

export function StudentAttendancePage() {
  const { student } = usePortal()
  const { t, date, weekday } = usePortalI18n()
  const now = new Date()
  const [[year, month], setMonth] = useState<[number, number]>([now.getFullYear(), now.getMonth() + 1])
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'attendance', student.id, year, month],
    queryFn: () => studentPortalApi.attendance(student.id, year, month),
    placeholderData: keepPreviousData,
  })
  return (
    <div>
      <PageTitle title={t('attendance.title')} actions={<MonthSwitcher year={year} month={month} onChange={(y, m) => setMonth([y, m])} />} />
      {isPending ? <Loading /> : isError || !data ? <LoadError onRetry={() => void refetch()} /> : (
        <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
          <PCard>
            <div className="flex flex-col items-center gap-4">
              <ProgressRing value={data.summary.percent} size={132} label={t('attendance.percent')} />
              <div className="grid w-full grid-cols-2 gap-2">
                <Stat label={t('attendance.attended')} value={data.summary.attended} accent />
                <Stat label={t('attendance.missed')} value={data.summary.absent + data.summary.excused} />
                <Stat label={t('attendance.late')} value={data.summary.late} />
                <Stat label={t('attendance.excused')} value={data.summary.excused} />
              </div>
            </div>
          </PCard>
          <PCard>
            {data.records.length === 0 ? <Empty>{t('attendance.empty')}</Empty> : (
              <ul className="divide-y divide-border/70">
                {data.records.map((record) => {
                  const day = (new Date(`${record.lesson.date}T00:00:00`).getDay() + 6) % 7
                  return (
                    <li key={record.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-ink">{weekday(day)}, {date(record.lesson.date)} · {record.lesson.start ?? ''}</p>
                        <p className="truncate text-xs text-ink-secondary">
                          {[record.lesson.subject?.name, record.lesson.topic, record.lesson.teacher?.name].filter(Boolean).join(' · ')}
                        </p>
                        {record.excuse_reason || record.comment ? <p className="mt-0.5 text-xs text-ink-muted">{record.excuse_reason || record.comment}</p> : null}
                      </div>
                      <AttendanceBadge mark={record.status} />
                    </li>
                  )
                })}
              </ul>
            )}
          </PCard>
        </div>
      )}
    </div>
  )
}

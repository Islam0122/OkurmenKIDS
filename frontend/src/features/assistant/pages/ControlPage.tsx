import { format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { AlertTriangle, ChevronRight, Eye, ShieldCheck } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useAssistantOptions, useControl } from '@/hooks/useAssistant'
import type { ControlCategory, ControlPeriod, StudentActivity } from '@/types/assistant'
import { cn } from '@/utils/cn'

import { useAssistantActions } from '../actions/AssistantActions'
import { ControlStatusBadge, Percent } from '../records/badges'

const PERIODS: { value: ControlPeriod; label: string }[] = [
  { value: '7d', label: '7 дней' }, { value: '14d', label: '14 дней' }, { value: '30d', label: '30 дней' },
  { value: 'month', label: 'Месяц' }, { value: 'all', label: 'Всё время' },
]
const SORTS = [
  { value: 'risk', label: 'Сначала проблемные' },
  { value: 'attendance', label: 'По посещаемости' },
  { value: 'homework', label: 'По выполнению ДЗ' },
  { value: 'absences', label: 'По пропускам подряд' },
  { value: 'missed_homework', label: 'По несданным ДЗ' },
  { value: 'last_activity', label: 'По последней активности' },
]
/** The four headline categories, in the order they read. */
const KPIS: { key: ControlCategory; label: string; tone: string }[] = [
  { key: 'not_attending', label: 'Не ходят на уроки', tone: 'text-warning' },
  { key: 'no_homework', label: 'Не сдают ДЗ', tone: 'text-warning' },
  { key: 'both', label: 'Не ходят + не делают ДЗ', tone: 'text-danger' },
  { key: 'low_activity', label: 'Низкая активность', tone: 'text-danger' },
  { key: 'risk', label: 'В зоне риска', tone: 'text-danger' },
]

const day = (value: string | null) => (value ? format(parseISO(value), 'd MMM', { locale: ru }) : '—')

function Streak({ value, alert }: { value: number; alert: number }) {
  return <span className={cn('tabular-nums', value >= alert ? 'font-semibold text-danger' : value ? 'text-ink' : 'text-ink-muted')}>{value}</span>
}

/** «Контроль активности» — read only: who stops attending or doing homework, found by the system, not by hand. */
export function AssistantControlPage() {
  const [params, setParams] = useSearchParams()
  const period = (PERIODS.some((p) => p.value === params.get('period')) ? params.get('period') : '30d') as ControlPeriod
  const category = (params.get('category') ?? '') as ControlCategory | ''
  const group = params.get('group') ?? ''
  const sort = params.get('sort') ?? 'risk'
  const { open } = useAssistantActions()
  const { data: options } = useAssistantOptions()
  const { data, isPending, isError, refetch } = useControl({
    period, category: category || undefined, group: group ? Number(group) : undefined, sort,
  })
  const set = (key: string, value: string, fallback: string) => {
    const next = new URLSearchParams(params)
    if (!value || value === fallback) next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }
  const alertAbs = data?.thresholds.consecutive_absences ?? 3
  const alertHw = data?.thresholds.consecutive_missed_homework ?? 3
  const openStudent = (row: StudentActivity) => open({ type: 'control-student', studentId: row.student_id, period })

  return (
    <div>
      <PageHeader title="Контроль активности" description="Кто перестаёт ходить на занятия и сдавать ДЗ. Считает система — по посещаемости и результатам ДЗ." />

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
        {KPIS.map((kpi) => {
          const active = category === kpi.key
          return (
            <button key={kpi.key} type="button" onClick={() => set('category', active ? '' : kpi.key, '')} aria-pressed={active}
              className={cn('card flex min-w-0 flex-col items-start px-3 py-2 text-left transition-colors hover:border-brand-200',
                active && 'border-brand-500 bg-brand-50')}>
              <span className={cn('text-xl leading-tight font-semibold tabular-nums', data?.kpis[kpi.key] ? kpi.tone : 'text-ink-muted')}>{data ? data.kpis[kpi.key] : '—'}</span>
              <span className="truncate text-xs text-ink-secondary">{kpi.label}</span>
            </button>
          )
        })}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <SegmentedControl aria-label="Период" options={PERIODS} value={period} onChange={(v) => set('period', v, '30d')} />
        <div className="w-full sm:w-44">
          <Select aria-label="Группа" value={group} placeholder="Все группы" onChange={(e) => set('group', e.target.value, '')}
            options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
        </div>
        <div className="w-full sm:w-56">
          <Select aria-label="Категория" value={category} placeholder="Все студенты" onChange={(e) => set('category', e.target.value, '')}
            options={(data?.categories ?? []).map((c) => ({ value: c.key, label: `${c.label} (${c.count})` }))} />
        </div>
        <div className="w-full sm:w-56">
          <Select aria-label="Сортировка" value={sort} onChange={(e) => set('sort', e.target.value, 'risk')} options={SORTS} />
        </div>
      </div>

      {isPending ? <LoadingState label="Анализируем активность…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && data.students.length === 0 ? (
        <EmptyState icon={ShieldCheck} title={category ? 'В этой категории никого нет' : 'Активных студентов нет'} description={category ? 'Хороший знак.' : undefined} />
      ) : null}
      {data && data.students.length > 0 ? (
        <section className="card overflow-hidden">
          <div className="max-h-[40rem] overflow-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead className="sticky top-0 z-10 bg-surface-muted text-left text-xs text-ink-secondary">
                <tr>
                  <th className="px-4 py-2 font-medium">Студент</th>
                  <th className="px-2 py-2 text-right font-medium">Посещаемость</th>
                  <th className="px-2 py-2 text-right font-medium">ДЗ</th>
                  <th className="px-2 py-2 text-right font-medium" title="Пропусков подряд">Пропуски подряд</th>
                  <th className="px-2 py-2 text-right font-medium" title="Несданных ДЗ подряд">ДЗ подряд</th>
                  <th className="px-2 py-2 font-medium">Последний урок</th>
                  <th className="px-2 py-2 font-medium">Последнее ДЗ</th>
                  <th className="px-4 py-2 font-medium">Статус</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.students.map((row) => (
                  <tr key={row.student_id} onClick={() => openStudent(row)} className="cursor-pointer hover:bg-surface-hover">
                    <td className="max-w-56 px-4 py-2">
                      <span className="flex items-center gap-1.5 font-medium text-ink">
                        {row.status === 'risk' ? <AlertTriangle className="size-3.5 shrink-0 text-danger" aria-hidden /> : null}
                        <span className="truncate">{row.name}</span>
                      </span>
                      <span className="block truncate text-xs text-ink-muted">{row.group?.name}{row.last_teacher ? ` · ${row.last_teacher}` : ''}</span>
                    </td>
                    <td className="px-2 py-2 text-right"><Percent value={row.attendance} /><span className="block text-2xs text-ink-muted tabular-nums">{row.attended}/{row.marked}</span></td>
                    <td className="px-2 py-2 text-right"><Percent value={row.homework} /><span className="block text-2xs text-ink-muted tabular-nums">{row.homework_done}/{row.homework_due}</span></td>
                    <td className="px-2 py-2 text-right"><Streak value={row.consecutive_absences} alert={alertAbs} /></td>
                    <td className="px-2 py-2 text-right"><Streak value={row.consecutive_missed_homework} alert={alertHw} /></td>
                    <td className="px-2 py-2 whitespace-nowrap text-ink-secondary">{day(row.last_attended)}</td>
                    <td className="px-2 py-2 whitespace-nowrap text-ink-secondary">{day(row.last_homework_done)}</td>
                    <td className="px-4 py-2"><span className="flex items-center gap-1"><ControlStatusBadge status={row.status} label={row.status_label} /><ChevronRight className="size-4 text-ink-muted" aria-hidden /></span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="flex items-center gap-1.5 border-t border-border px-4 py-2 text-xs text-ink-muted">
            <Eye className="size-3.5" aria-hidden />
            Только просмотр. Учитываются активные студенты начавших обучение групп, их текущая группа; неотмеченные занятия и ДЗ до дедлайна не считаются пропуском.
          </p>
        </section>
      ) : null}
    </div>
  )
}

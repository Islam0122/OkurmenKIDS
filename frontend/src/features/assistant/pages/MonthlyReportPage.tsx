import { useState } from 'react'
import type { ReactNode } from 'react'
import { format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { AlertTriangle, CheckCircle2, Download, Eye, FileBarChart, MessageSquareQuote, RefreshCw } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { extractErrorMessage } from '@/lib/apiError'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { useMonthlyReport } from '@/hooks/useAssistant'
import type { MonthlyReport, ReportStudent } from '@/types/assistant'
import { cn } from '@/utils/cn'

import { useAssistantActions } from '../actions/AssistantActions'
import { ControlStatusBadge, Percent, PercentBar } from '../records/badges'

const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
const FIRST_YEAR = 2024

const day = (value: string | null) => (value ? format(parseISO(value), 'd MMMM', { locale: ru }) : '—')
const money = (value: number) => `${Math.round(value).toLocaleString('ru-RU')} сом`

function Section({ index, title, hint, children }: { index: number; title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="space-y-3" aria-labelledby={`report-${index}`}>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h2 id={`report-${index}`} className="text-lg font-semibold text-ink">
          <span className="mr-1.5 text-ink-muted tabular-nums">{index}.</span>{title}
        </h2>
        {hint ? <span className="text-xs text-ink-muted">{hint}</span> : null}
      </div>
      {children}
    </section>
  )
}

function Kpi({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="card min-w-0 px-3 py-2">
      <span className={cn('block text-xl leading-tight font-semibold tabular-nums text-ink', tone)}>{value}</span>
      <span className="block truncate text-xs text-ink-secondary">{label}</span>
    </div>
  )
}

function KpiGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <h3 className="mb-1.5 text-xs font-semibold tracking-wide text-ink-muted uppercase">{title}</h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{children}</div>
    </div>
  )
}

function Table({ head, children, empty }: { head: ReactNode; children: ReactNode; empty?: string | false }) {
  if (empty) return <p className="card px-4 py-3 text-sm text-ink-secondary">{empty}</p>
  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead className="bg-surface-muted text-left text-xs text-ink-secondary">{head}</thead>
          <tbody className="divide-y divide-border">{children}</tbody>
        </table>
      </div>
    </div>
  )
}

const th = 'px-3 py-2 font-medium first:pl-4 last:pr-4'
const td = 'px-3 py-2 first:pl-4 last:pr-4'
const num = 'text-right tabular-nums'

function StudentName({ row }: { row: ReportStudent }) {
  const { open } = useAssistantActions()
  return (
    <button type="button" className="text-left font-medium text-ink hover:text-brand-700"
      onClick={() => open({ type: 'control-student', studentId: row.student_id, period: 'month' })}>
      {row.name}
    </button>
  )
}

function Streak({ value }: { value: number }) {
  return <span className={cn('tabular-nums', value >= 3 ? 'font-semibold text-danger' : value ? 'text-ink' : 'text-ink-muted')}>{value}</span>
}

function Totals({ items }: { items: [string, ReactNode, string?][] }) {
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
      {items.map(([label, value, tone]) => (
        <span key={label} className="text-ink-secondary">{label}: <b className={cn('font-semibold text-ink tabular-nums', tone)}>{value}</b></span>
      ))}
    </div>
  )
}

function Headline({ label, value, children }: { label: string; value: number | null; children?: ReactNode }) {
  return (
    <div className="card space-y-2 px-4 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-medium text-ink">{label}</span>
        <Percent value={value} className="text-2xl font-semibold" />
      </div>
      <PercentBar value={value} />
      {children}
    </div>
  )
}

function Report({ report }: { report: MonthlyReport }) {
  const { overview: o, attendance: att, homework: hw, students: st, surveys: sv, scholarships: sch, conclusions } = report
  const act = st.activity
  return (
    <div className="space-y-8">
      <Section index={1} title="Общая статистика">
        <div className="space-y-3">
          <KpiGroup title="Группы">
            <Kpi label="Всего групп" value={o.groups_total} />
            <Kpi label="Активных" value={o.groups_active} tone="text-brand-700" />
            <Kpi label="Неактивных" value={o.groups_inactive} />
          </KpiGroup>
          <KpiGroup title="Студенты">
            <Kpi label="Всего студентов" value={o.students_total} />
            <Kpi label="Активных" value={o.students_active} tone="text-brand-700" />
            <Kpi label="Новых за месяц" value={o.students_new} />
            <Kpi label="Деактивировано" value={o.students_deactivated} tone={o.students_deactivated ? 'text-warning' : undefined} />
          </KpiGroup>
          <KpiGroup title="Учебная активность">
            <Kpi label="Средняя посещаемость" value={<Percent value={o.attendance_percent} />} />
            <Kpi label="Среднее выполнение ДЗ" value={<Percent value={o.homework_percent} />} />
            <Kpi label="В зоне риска" value={o.students_at_risk} tone={o.students_at_risk ? 'text-danger' : undefined} />
          </KpiGroup>
        </div>
      </Section>

      <Section index={2} title="Посещаемость" hint="Только проведённые занятия, отменённые не учитываются">
        <Headline label="Посещаемость" value={att.percent}>
          <Totals items={[['Проведено занятий', att.lessons], ['Присутствовали', att.attended, 'text-brand-700'],
            ['Пропустили', att.absent, att.absent ? 'text-danger' : undefined], ['Уважительная причина', att.excused], ['Всего отметок', att.marked]]} />
        </Headline>
        <Table empty={att.groups.length === 0 && 'В этом месяце занятий не было.'} head={
          <tr><th className={th}>Группа</th><th className={cn(th, num)}>Студенты</th><th className={cn(th, num)}>Занятий</th>
            <th className={cn(th, num)}>Пропуски</th><th className={cn(th, 'w-40')}>Посещаемость</th></tr>
        }>
          {att.groups.map((g) => (
            <tr key={g.group.id}>
              <td className={cn(td, 'font-medium text-ink')}>{g.group.name}</td>
              <td className={cn(td, num)}>{g.students}</td>
              <td className={cn(td, num)}>{g.lessons}</td>
              <td className={cn(td, num)}>{g.absent}</td>
              <td className={td}><div className="flex items-center gap-2"><PercentBar value={g.percent} className="flex-1" /><Percent value={g.percent} className="w-10 text-right" /></div></td>
            </tr>
          ))}
        </Table>
      </Section>

      <Section index={3} title="Требуют внимания — посещаемость">
        <Table empty={st.attendance_attention.length === 0 && 'Студентов с низкой посещаемостью нет.'} head={
          <tr><th className={th}>Студент</th><th className={th}>Группа</th><th className={cn(th, num)}>Посещаемость</th>
            <th className={cn(th, num)}>Пропуски</th><th className={cn(th, num)}>Пропуски подряд</th></tr>
        }>
          {st.attendance_attention.map((r) => (
            <tr key={r.student_id}>
              <td className={td}><StudentName row={r} /></td>
              <td className={cn(td, 'text-ink-secondary')}>{r.group?.name}</td>
              <td className={cn(td, num)}><Percent value={r.attendance} /> <span className="text-2xs text-ink-muted">{r.attended}/{r.marked}</span></td>
              <td className={cn(td, num)}>{r.absent}</td>
              <td className={cn(td, num)}><Streak value={r.consecutive_absences} /></td>
            </tr>
          ))}
        </Table>
      </Section>

      <Section index={4} title="Домашние задания" hint="Выполнение — по заданиям, чей дедлайн уже прошёл">
        <Headline label="Выполнение ДЗ" value={hw.percent}>
          <Totals items={[['Выдано заданий', hw.given], ['Выполнено работ', hw.done, 'text-brand-700'],
            ['Не выполнено', hw.not_done, hw.not_done ? 'text-danger' : undefined], ['На проверке', hw.pending, hw.pending ? 'text-info' : undefined]]} />
        </Headline>
        <Table empty={hw.groups.length === 0 && 'В этом месяце ДЗ не выдавали.'} head={
          <tr><th className={th}>Группа</th><th className={cn(th, num)}>ДЗ</th><th className={cn(th, num)}>Выполнено</th>
            <th className={cn(th, num)}>Не выполнено</th><th className={cn(th, num)}>На проверке</th><th className={cn(th, 'w-40')}>Выполнение</th></tr>
        }>
          {hw.groups.map((g) => (
            <tr key={g.group.id}>
              <td className={cn(td, 'font-medium text-ink')}>{g.group.name}</td>
              <td className={cn(td, num)}>{g.homeworks}</td>
              <td className={cn(td, num)}>{g.done}</td>
              <td className={cn(td, num)}>{g.not_done}</td>
              <td className={cn(td, num)}>{g.pending}</td>
              <td className={td}><div className="flex items-center gap-2"><PercentBar value={g.percent} className="flex-1" /><Percent value={g.percent} className="w-10 text-right" /></div></td>
            </tr>
          ))}
        </Table>
      </Section>

      <Section index={5} title="Требуют внимания — ДЗ">
        <Table empty={st.homework_attention.length === 0 && 'Студентов, которые не сдают ДЗ, нет.'} head={
          <tr><th className={th}>Студент</th><th className={th}>Группа</th><th className={cn(th, num)}>Выполнение</th>
            <th className={cn(th, num)}>Не сдано</th><th className={cn(th, num)}>Подряд</th></tr>
        }>
          {st.homework_attention.map((r) => (
            <tr key={r.student_id}>
              <td className={td}><StudentName row={r} /></td>
              <td className={cn(td, 'text-ink-secondary')}>{r.group?.name}</td>
              <td className={cn(td, num)}><Percent value={r.homework} /> <span className="text-2xs text-ink-muted">{r.homework_done}/{r.homework_due}</span></td>
              <td className={cn(td, num)}>{r.homework_missed}</td>
              <td className={cn(td, num)}><Streak value={r.consecutive_missed_homework} /></td>
            </tr>
          ))}
        </Table>
      </Section>

      <Section index={6} title="В зоне риска" hint="Низкая посещаемость и низкое выполнение ДЗ одновременно">
        {st.risk.length === 0 ? <p className="card px-4 py-3 text-sm text-ink-secondary">Студентов в зоне риска нет.</p> : (
          <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {st.risk.map((r) => (
              <li key={r.student_id} className="card space-y-2 border-danger/30 px-4 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="flex items-center gap-1.5"><AlertTriangle className="size-4 shrink-0 text-danger" aria-hidden /><StudentName row={r} /></span>
                    <span className="block text-xs text-ink-muted">{r.group?.name}</span>
                  </div>
                  <ControlStatusBadge status={r.status} label={r.status_label} />
                </div>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                  <dt className="text-ink-secondary">Посещаемость</dt><dd className="text-right font-semibold"><Percent value={r.attendance} /></dd>
                  <dt className="text-ink-secondary">ДЗ</dt><dd className="text-right font-semibold"><Percent value={r.homework} /></dd>
                  <dt className="text-ink-secondary">Пропуски подряд</dt><dd className="text-right"><Streak value={r.consecutive_absences} /></dd>
                  <dt className="text-ink-secondary">ДЗ не сдано подряд</dt><dd className="text-right"><Streak value={r.consecutive_missed_homework} /></dd>
                  <dt className="text-ink-secondary">Последняя активность</dt><dd className="text-right text-ink">{day(r.last_activity)}</dd>
                </dl>
                <p className="text-xs font-medium text-danger">Причина: {r.reason}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section index={7} title="Опросы">
        {sv.surveys === 0 ? <p className="card px-4 py-3 text-sm text-ink-secondary">В этом месяце опросов и ответов не было.</p> : (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Kpi label="Опросов" value={sv.surveys} />
              <Kpi label="Участников (ответов)" value={sv.participants} />
              <Kpi label="Участие" value={<Percent value={sv.participation} />} />
              <Kpi label="Средняя оценка" value={sv.average !== null ? <>{sv.average}<span className="text-sm font-normal text-ink-muted"> / 5</span></> : '—'} />
            </div>
            <Table head={
              <tr><th className={th}>Опрос</th><th className={th}>Группа</th><th className={cn(th, num)}>Участников</th>
                <th className={cn(th, num)}>Средняя оценка</th><th className={cn(th, num)}>Низкие оценки</th></tr>
            }>
              {sv.rows.map((s) => (
                <tr key={s.id}>
                  <td className={td}><span className="font-medium text-ink">{s.title}</span><span className="block text-2xs text-ink-muted">{s.audience_display} · {s.status_display}</span></td>
                  <td className={cn(td, 'text-ink-secondary')}>{s.group?.name ?? 'Все'}</td>
                  <td className={cn(td, num)}>{s.expected ? `${s.participants}/${s.expected}` : s.participants}
                    {s.participation !== null ? <span className="block text-2xs text-ink-muted">{s.participation}%</span> : null}</td>
                  <td className={cn(td, num)}>{s.average ?? '—'}</td>
                  <td className={cn(td, num, s.low_ratings ? 'font-semibold text-danger' : 'text-ink-muted')}>{s.low_ratings}</td>
                </tr>
              ))}
            </Table>
            <p className="text-xs text-ink-muted">
              Средняя оценка — по вопросам с числовой шкалой (1–5, 1–10), приведена к 5. Участие — только для опросов группы, к её активным студентам.
              Низкая оценка — 40% шкалы и ниже.
            </p>
            {sv.quotes.length ? (
              <div className="card px-4 py-3">
                <h3 className="mb-2 flex items-center gap-1.5 font-semibold text-ink"><MessageSquareQuote className="size-4 text-brand-700" aria-hidden />Что говорят студенты</h3>
                <ul className="space-y-2">
                  {sv.quotes.map((q, i) => (
                    <li key={i} className="border-l-2 border-brand-200 pl-3 text-sm">
                      <p className="text-ink">«{q.text}»{q.count > 1 ? <span className="ml-1.5 rounded-full bg-brand-50 px-1.5 py-0.5 text-2xs font-medium text-brand-700">×{q.count}</span> : null}</p>
                      <p className="text-2xs text-ink-muted">{q.survey} · {q.question} · {day(q.date)}</p>
                    </li>
                  ))}
                </ul>
                {sv.texts_total > sv.quotes.length ? <p className="mt-2 text-xs text-ink-muted">Показаны повторяющиеся и последние ответы: {sv.quotes.length} из {sv.texts_total}.</p> : null}
              </div>
            ) : null}
          </>
        )}
      </Section>

      <Section index={8} title="Стипендии">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Kpi label="Стипендий" value={sch.awards} />
          <Kpi label="Получателей" value={sch.recipients} />
          <Kpi label="Общая сумма" value={money(sch.total_amount)} />
          <Kpi label="Выдано на руки" value={sch.paid ? `${sch.paid} · ${money(sch.paid_amount)}` : '0'} />
        </div>
        <Table empty={sch.rows.length === 0 && 'В этом месяце стипендии не начислялись.'} head={
          <tr><th className={th}>Студент</th><th className={th}>Группа</th><th className={th}>Стипендия</th>
            <th className={cn(th, num)}>Сумма</th><th className={th}>Причина</th><th className={th}>Статус</th></tr>
        }>
          {sch.rows.map((a) => (
            <tr key={a.id}>
              <td className={cn(td, 'font-medium text-ink')}>{a.student.name}</td>
              <td className={cn(td, 'text-ink-secondary')}>{a.group || '—'}</td>
              <td className={td}>{a.title}</td>
              <td className={cn(td, num, 'whitespace-nowrap')}>{money(a.amount)}</td>
              <td className={cn(td, 'text-ink-secondary')}>{a.reason}</td>
              <td className={cn(td, 'text-xs whitespace-nowrap text-ink-secondary')}>{a.status_display}<span className="block">{a.payment_display}</span></td>
            </tr>
          ))}
        </Table>
      </Section>

      <Section index={9} title="Активность студентов" hint={`Активные студенты начавших обучение групп: ${act.analysed}`}>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <Kpi label="Активные (норма)" value={act.normal} tone="text-brand-700" />
          <Kpi label="Требуют внимания" value={act.attention} tone={act.attention ? 'text-warning' : undefined} />
          <Kpi label="Низкая активность" value={act.low} tone={act.low ? 'text-danger' : undefined} />
          <Kpi label="Не посещают" value={act.not_attending} tone={act.not_attending ? 'text-danger' : undefined} />
          <Kpi label="Не сдают ДЗ" value={act.no_homework} tone={act.no_homework ? 'text-danger' : undefined} />
          <Kpi label="Без активности" value={act.no_activity} tone={act.no_activity ? 'text-danger' : undefined} />
        </div>
        {st.no_activity.length ? (
          <p className="text-sm text-ink-secondary">
            Без активности за месяц (ни одного посещения и сданного ДЗ):{' '}
            {st.no_activity.map((r, i) => <span key={r.student_id}>{i ? ', ' : ''}<StudentName row={r} /> <span className="text-ink-muted">({r.group?.name})</span></span>)}
          </p>
        ) : null}
        {act.no_data ? <p className="text-xs text-ink-muted">Мало данных для оценки (нет отметок и ДЗ к сроку): {act.no_data}.</p> : null}
      </Section>

      <Section index={10} title="Итоги месяца">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="card px-4 py-3">
            <h3 className="mb-2 flex items-center gap-1.5 font-semibold text-brand-700"><CheckCircle2 className="size-4" aria-hidden />Хорошие показатели</h3>
            {conclusions.good.length ? <ul className="list-disc space-y-1 pl-5 text-sm text-ink">{conclusions.good.map((line) => <li key={line}>{line}</li>)}</ul>
              : <p className="text-sm text-ink-muted">Нет показателей выше нормы.</p>}
          </div>
          <div className="card px-4 py-3">
            <h3 className="mb-2 flex items-center gap-1.5 font-semibold text-warning"><AlertTriangle className="size-4" aria-hidden />Требует внимания</h3>
            {conclusions.attention.length ? <ul className="list-disc space-y-1 pl-5 text-sm text-ink">{conclusions.attention.map((line) => <li key={line}>{line}</li>)}</ul>
              : <p className="text-sm text-ink-muted">Проблем не найдено.</p>}
          </div>
        </div>
        <p className="text-sm text-ink-secondary">
          Группы, требующие внимания: <b className="font-semibold text-ink">{conclusions.groups.length ? conclusions.groups.join(', ') : 'нет'}</b>
        </p>
        <Table empty={conclusions.students.length === 0 && 'Студентов, требующих внимания, нет.'} head={
          <tr><th className={th}>Студент, требующий внимания</th><th className={th}>Группа</th><th className={th}>Причина</th></tr>
        }>
          {conclusions.students.map((x) => (
            <tr key={x.student_id}>
              <td className={cn(td, 'font-medium text-ink')}>{x.name}</td>
              <td className={cn(td, 'text-ink-secondary')}>{x.group || '—'}</td>
              <td className={cn(td, 'text-ink-secondary')}>{x.reason}</td>
            </tr>
          ))}
        </Table>
      </Section>
    </div>
  )
}

/** «Месячный отчёт» — one month, one page; read only, computed from existing data on request. */
export function AssistantMonthlyReportPage() {
  const now = new Date()
  const [params, setParams] = useSearchParams()
  const year = Number(params.get('year')) || now.getFullYear()
  const month = Number(params.get('month')) || now.getMonth() + 1
  const [draft, setDraft] = useState({ year, month })
  const { data, isPending, isFetching, isError, error, refetch } = useMonthlyReport(year, month)

  const years = Array.from({ length: now.getFullYear() - FIRST_YEAR + 1 }, (_, i) => now.getFullYear() - i)
  const maxMonth = draft.year === now.getFullYear() ? now.getMonth() + 1 : 12
  const generate = () => {
    const next = { year: draft.year, month: Math.min(draft.month, maxMonth) }
    if (next.year === year && next.month === month) void refetch()
    else setParams({ year: String(next.year), month: String(next.month) }, { replace: true })
  }
  const message = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail
  const { showToast } = useToast()
  const [downloading, setDownloading] = useState(false)
  // The PDF is always the report on screen: its own year and month, never the picker's draft.
  const downloadPdf = async () => {
    if (!data) return
    setDownloading(true)
    try {
      await assistantApi.downloadMonthlyReportPdf(data.year, data.month)
    } catch (err) {
      showToast(`Не удалось сформировать PDF: ${extractErrorMessage(err)}`, 'error')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div>
      <PageHeader title="Месячный отчёт" description="Сводный отчёт по студентам и группам за выбранный месяц." />
      <div className="card mb-6 flex flex-wrap items-end gap-3 px-4 py-3">
        <label className="w-full text-xs text-ink-secondary sm:w-40">Месяц
          <Select aria-label="Месяц" value={String(Math.min(draft.month, maxMonth))} className="mt-1"
            onChange={(e) => setDraft((d) => ({ ...d, month: Number(e.target.value) }))}
            options={MONTHS.slice(0, maxMonth).map((label, i) => ({ value: String(i + 1), label }))} />
        </label>
        <label className="w-full text-xs text-ink-secondary sm:w-32">Год
          <Select aria-label="Год" value={String(draft.year)} className="mt-1"
            onChange={(e) => setDraft((d) => ({ ...d, year: Number(e.target.value) }))}
            options={years.map((y) => ({ value: String(y), label: String(y) }))} />
        </label>
        <Button leftIcon={<FileBarChart className="size-4" aria-hidden />} onClick={generate} isLoading={isFetching && !isPending}>Сформировать отчёт</Button>
        {data ? (
          <span className="flex items-center gap-1.5 text-xs text-ink-muted sm:ml-auto">
            <RefreshCw className="size-3.5" aria-hidden />
            Сформирован {format(parseISO(data.generated_at), 'd MMM, HH:mm', { locale: ru })}
          </span>
        ) : null}
      </div>

      {isPending ? <LoadingState label="Формируем отчёт…" /> : null}
      {isError && !data ? (message ? <EmptyState icon={FileBarChart} title={message} /> : <ErrorState onRetry={() => void refetch()} />) : null}
      {data ? (
        <>
          <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-2xl font-semibold text-ink">{data.title}</h2>
              <span className="text-sm text-ink-secondary">
                {format(parseISO(data.start), 'dd.MM.yyyy')} — {format(parseISO(data.end), 'dd.MM.yyyy')}
                {!data.is_complete ? ` · месяц идёт, данные по ${format(parseISO(data.until), 'd MMMM', { locale: ru })}` : ''}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" leftIcon={<RefreshCw className="size-4" aria-hidden />} onClick={() => void refetch()}
                isLoading={isFetching && !isPending} disabled={downloading}>Обновить</Button>
              <Button leftIcon={<Download className="size-4" aria-hidden />} onClick={() => void downloadPdf()}
                isLoading={downloading} disabled={isFetching}>
                {downloading ? 'Генерация PDF…' : 'Скачать PDF'}
              </Button>
            </div>
          </div>
          <Report report={data} />
          <p className="mt-8 flex items-center gap-1.5 border-t border-border pt-3 text-xs text-ink-muted">
            <Eye className="size-3.5" aria-hidden />
            Только просмотр: отчёт считается из посещаемости, ДЗ, опросов и стипендий и ничего не меняет. Отчёт по тренерам — у Team Lead.
          </p>
        </>
      ) : null}
    </div>
  )
}

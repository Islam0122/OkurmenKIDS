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
import { useAssistantOptions, useMonthlyReport } from '@/hooks/useAssistant'
import type { MonthlyReport, ReportFilters, ReportStudent } from '@/types/assistant'
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

function Bullets({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <p className="card px-4 py-3 text-sm text-ink-muted">{empty}</p>
  return <ul className="card list-disc space-y-1 py-3 pr-4 pl-9 text-sm text-ink">{items.map((line) => <li key={line}>{line}</li>)}</ul>
}

function Bars({ items, tone = 'bg-brand-500' }: { items: { label: string; count: number; percent: number | null }[]; tone?: string }) {
  const top = Math.max(1, ...items.map((x) => x.count))
  return (
    <ul className="card space-y-2 px-4 py-3" role="list">
      {items.map((x) => (
        <li key={x.label} className="grid grid-cols-[minmax(0,10rem)_1fr_auto] items-center gap-3 text-sm sm:grid-cols-[minmax(0,16rem)_1fr_auto]">
          <span className="min-w-0 break-words text-ink">{x.label}</span>
          <span className="h-2 overflow-hidden rounded-full bg-surface-hover">
            <span className={cn('block h-full rounded-full', tone)} style={{ width: `${(x.count / top) * 100}%` }} />
          </span>
          <span className="text-right font-semibold whitespace-nowrap text-ink tabular-nums">{x.count}{x.percent !== null ? ` · ${x.percent}%` : ''}</span>
        </li>
      ))}
    </ul>
  )
}

const dateShort = (value: string | null) => (value ? format(parseISO(value), 'dd.MM.yyyy') : '—')

function InactiveSection({ index, report }: { index: number; report: MonthlyReport }) {
  const { thresholds: [short, mid, long], counts: c, previous, students } = report.inactive
  return (
    <Section index={index} title="Неактивные студенты и динамика активности"
      hint={`Активные на конец месяца; дни без посещения и сданного ДЗ, пока шли занятия. Пороги ${short} / ${mid} / ${long} дней`}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Активные" value={c.active} tone="text-brand-700" />
        <Kpi label={`Неактивные (${mid}+ дн.)`} value={c.inactive} tone={c.inactive ? 'text-warning' : undefined} />
        <Kpi label="Без посещений" value={c.no_attendance} tone={c.no_attendance ? 'text-danger' : undefined} />
        <Kpi label="Не сдают ДЗ" value={c.no_homework} tone={c.no_homework ? 'text-danger' : undefined} />
        <Kpi label="В зоне риска" value={c.risk} tone={c.risk ? 'text-danger' : undefined} />
        <Kpi label={`Давно (${long}+ дн.)`} value={c.long_inactive} tone={c.long_inactive ? 'text-danger' : undefined} />
      </div>
      {previous ? (
        <p className="text-sm text-ink-secondary">
          К прошлому месяцу: неактивны {mid}+ дней — {previous.inactive} → <b className="text-ink">{c.inactive}</b>; в зоне риска — {previous.risk} → <b className="text-ink">{c.risk}</b>.
        </p>
      ) : null}
      <Bars tone="bg-warning" items={report.inactive.thresholds.map((d) => ({ label: `${d}+ дней без активности`, count: c[`idle_${d}`] ?? 0, percent: null }))} />
      <Table empty={students.length === 0 && 'Неактивных студентов нет.'} head={
        <tr><th className={th}>Студент</th><th className={th}>Группа · тренер</th><th className={th}>Посл. посещение</th><th className={th}>Посл. ДЗ</th>
          <th className={cn(th, num)}>Пропуски</th><th className={cn(th, num)}>Посещ.</th><th className={cn(th, num)}>ДЗ</th>
          <th className={cn(th, num)}>Без активности</th><th className={th}>Статус</th><th className={th}>Действие</th></tr>
      }>
        {students.map((x) => (
          <tr key={x.student_id}>
            <td className={cn(td, 'font-medium text-ink')}>{x.name}</td>
            <td className={cn(td, 'text-ink-secondary')}>{x.group?.name ?? '—'}{x.trainer ? <span className="block text-2xs text-ink-muted">{x.trainer}</span> : null}</td>
            <td className={cn(td, 'whitespace-nowrap')}>{dateShort(x.last_attended)}</td>
            <td className={cn(td, 'whitespace-nowrap')}>{dateShort(x.last_homework)}</td>
            <td className={cn(td, num)}>{x.absent}</td>
            <td className={cn(td, num)}><Percent value={x.attendance} /></td>
            <td className={cn(td, num)}><Percent value={x.homework} /></td>
            <td className={cn(td, num, (x.days_inactive ?? 0) >= long ? 'font-semibold text-danger' : (x.days_inactive ?? 0) >= mid ? 'text-warning' : '')}>
              {x.days_inactive === null ? '—' : `${x.days_inactive} дн.`}
            </td>
            <td className={cn(td, 'text-xs')}>{x.status}<span className="block text-ink-muted">{x.activity_label}</span></td>
            <td className={cn(td, 'min-w-48 text-xs text-ink')}>{x.action}</td>
          </tr>
        ))}
      </Table>
    </Section>
  )
}

function DeparturesSection({ index, report, filterBar }: { index: number; report: MonthlyReport; filterBar: ReactNode }) {
  const d = report.departures
  return (
    <Section index={index} title="Деактивированные студенты" hint="Ушли за месяц. Завершение обучения и пауза — отдельно; неактивные, но не ушедшие — не здесь">
      {filterBar}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Ушли за месяц" value={d.total} tone={d.total ? 'text-danger' : undefined} />
        <Kpi label="Уже вернулись" value={d.returned} tone={d.returned ? 'text-brand-700' : undefined} />
        <Kpi label="Доля вернувшихся" value={<Percent value={d.returned_percent} />} />
        <Kpi label="Причина не указана" value={d.unknown} tone={d.unknown ? 'text-warning' : undefined} />
        <Kpi label="Завершили обучение" value={d.completed} />
        <Kpi label="Ушли на паузу" value={d.paused} />
      </div>
      <Table empty={d.rows.length === 0 && (d.filters_label ? 'По выбранным фильтрам уходов нет.' : 'За месяц никто не ушёл.')} head={
        <tr><th className={th}>Студент</th><th className={th}>Группа · тренер</th><th className={th}>Дата</th><th className={th}>Причина</th>
          <th className={th}>Оформил</th><th className={th}>Посл. активность</th><th className={cn(th, num)}>Срок обучения</th><th className={th}>Возврат</th></tr>
      }>
        {d.rows.map((x) => (
          <tr key={x.event_id}>
            <td className={cn(td, 'font-medium text-ink')}>{x.name}</td>
            <td className={cn(td, 'text-ink-secondary')}>{x.group?.name ?? '—'}{x.trainer ? <span className="block text-2xs text-ink-muted">{x.trainer}</span> : null}</td>
            <td className={cn(td, 'whitespace-nowrap')}>{dateShort(x.date)}</td>
            <td className={cn(td, x.reason === 'unknown' ? 'text-warning' : 'text-ink')}>{x.reason_label}
              {x.comment ? <span className="block text-2xs text-ink-muted">{x.comment}</span> : null}</td>
            <td className={cn(td, 'text-ink-secondary')}>{x.performed_by || '—'}</td>
            <td className={cn(td, 'whitespace-nowrap')}>{dateShort(x.last_activity)}</td>
            <td className={cn(td, num)}>{x.study_days === null ? '—' : `${x.study_days} дн.`}</td>
            <td className={cn(td, 'whitespace-nowrap', x.returned_on ? 'text-brand-700' : 'text-ink-muted')}>{x.returned_on ? `Вернулся ${dateShort(x.returned_on)}` : '—'}</td>
          </tr>
        ))}
      </Table>
    </Section>
  )
}

function ReasonsSection({ index, report }: { index: number; report: MonthlyReport }) {
  const d = report.departures
  const change = d.change
  return (
    <Section index={index} title="Причины ухода" hint="Почему студенты уходят">
      <p className="text-sm text-ink-secondary">
        Ушли за месяц: <b className="text-ink">{d.month_total}</b>
        {d.previous_total !== null ? <> · в прошлом месяце {d.previous_total} ({change && change > 0 ? '+' : ''}{change})</> : null}
        {d.filters_label ? <> · по фильтрам ({d.filters_label}): <b className="text-ink">{d.total}</b></> : null}
        {' '}· вернулись {d.returned} ({d.returned_percent ?? '—'}%) · причина не указана: {d.unknown}
      </p>
      {d.total === 0 ? <p className="card px-4 py-3 text-sm text-ink-secondary">Уходов нет — распределять нечего.</p> : (
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="space-y-2 lg:col-span-2"><h3 className="text-sm font-semibold text-ink">По причинам</h3><Bars tone="bg-danger" items={d.by_reason} /></div>
          <div className="space-y-2"><h3 className="text-sm font-semibold text-ink">По группам</h3><Bars items={d.by_group} /></div>
          <div className="space-y-2"><h3 className="text-sm font-semibold text-ink">По тренерам групп</h3><Bars items={d.by_trainer} /></div>
        </div>
      )}
    </Section>
  )
}

function FinanceSection({ index, report }: { index: number; report: MonthlyReport }) {
  const f = report.finance
  return (
    <Section index={index} title="Финансовая аналитика">
      {!f.allowed ? <p className="card px-4 py-3 text-sm text-ink-secondary">{f.note}</p> : (
        <>
          <p className="rounded-lg bg-warning-soft px-4 py-3 text-sm text-warning">{f.note} Суммы не оцениваются и не придумываются.</p>
          <Table head={<tr><th className={th}>Показатель</th><th className={cn(th, num)}>Значение</th></tr>}>
            {f.metrics.map((m) => (
              <tr key={m.label}>
                <td className={td}>{m.label}</td>
                <td className={cn(td, num, m.value === null && 'text-ink-muted')}>{m.value ?? 'Недостаточно данных'}</td>
              </tr>
            ))}
          </Table>
          <p className="text-sm text-ink-secondary">Каких данных не хватает: {f.missing.join('; ')}.</p>
        </>
      )}
    </Section>
  )
}

function ComparisonSection({ index, report }: { index: number; report: MonthlyReport }) {
  const comp = report.comparison
  const trend = { better: ['▲ лучше', 'text-brand-700'], worse: ['▼ хуже', 'text-danger'], same: ['без изменений', 'text-ink-muted'] } as const
  return (
    <Section index={index} title="Сравнение с предыдущим месяцем" hint={`${comp.previous_title} → ${report.title}`}>
      <Table head={<tr><th className={th}>Показатель</th><th className={cn(th, num)}>{comp.previous_title}</th>
        <th className={cn(th, num)}>{report.title}</th><th className={cn(th, num)}>Изменение</th></tr>}>
        {comp.rows.map((x) => (
          <tr key={x.key}>
            <td className={td}>{x.label}</td>
            <td className={cn(td, num)}>{x.previous ?? '—'}</td>
            <td className={cn(td, num, 'font-semibold')}>{x.current ?? '—'}</td>
            <td className={cn(td, num, x.trend ? trend[x.trend][1] : 'text-ink-muted')}>
              {x.trend ? `${(x.delta ?? 0) > 0 ? '+' : ''}${x.delta} · ${trend[x.trend][0]}` : 'нет данных'}
            </td>
          </tr>
        ))}
      </Table>
    </Section>
  )
}

function ManagementSummary({ report }: { report: MonthlyReport }) {
  const m = report.summary
  const block = (title: string, items: string[], empty: string, tone: string) => (
    <div className="card px-4 py-3">
      <h4 className={cn('mb-1.5 text-sm font-semibold', tone)}>{title}</h4>
      {items.length ? <ul className="list-disc space-y-1 pl-5 text-sm text-ink">{items.map((line) => <li key={line}>{line}</li>)}</ul>
        : <p className="text-sm text-ink-muted">{empty}</p>}
    </div>
  )
  return (
    <div className="space-y-3">
      <h3 className="pt-2 text-base font-semibold text-ink">Управленческое резюме</h3>
      <div className="grid gap-3 md:grid-cols-2">
        {block('Что улучшилось', m.improved, 'Нет показателей, которые улучшились.', 'text-brand-700')}
        {block('Что ухудшилось', m.worsened, 'Нет показателей, которые ухудшились.', 'text-danger')}
        {block('Группы, требующие внимания', m.groups, 'Нет.', 'text-warning')}
        {block('Частые причины ухода', m.top_reasons, 'Уходов за месяц не было.', 'text-warning')}
      </div>
      <p className="rounded-lg bg-warning-soft px-4 py-2 text-sm text-ink">Потенциально нуждаются в контакте: <b>{m.contacts}</b></p>
      {block('Действия на следующий месяц', m.next_month, 'Нет данных для рекомендаций.', 'text-brand-700')}
    </div>
  )
}

function Report({ report, filterBar }: { report: MonthlyReport; filterBar: ReactNode }) {
  const { overview: o, attendance: att, homework: hw, students: st, surveys: sv, scholarships: sch, conclusions } = report
  // Sections are numbered in the order they appear — reordering never leaves a gap or a duplicate.
  let sectionNo = 0
  const next = () => (sectionNo += 1)
  const act = st.activity
  return (
    <div className="space-y-8">
      <Section index={next()} title="Общая статистика">
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

      <Section index={next()} title="Посещаемость" hint="Только проведённые занятия, отменённые не учитываются">
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

      <Section index={next()} title="Требуют внимания — посещаемость">
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

      <Section index={next()} title="Домашние задания" hint="Выполнение — по заданиям, чей дедлайн уже прошёл">
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

      <Section index={next()} title="Требуют внимания — ДЗ">
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

      <Section index={next()} title="В зоне риска" hint="Низкая посещаемость и низкое выполнение ДЗ одновременно">
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

      <Section index={next()} title="Опросы">
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

      <Section index={next()} title="Стипендии">
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

      <Section index={next()} title="Активность студентов" hint={`Активные студенты начавших обучение групп: ${act.analysed}`}>
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

      <InactiveSection index={next()} report={report} />
      <DeparturesSection index={next()} report={report} filterBar={filterBar} />
      <ReasonsSection index={next()} report={report} />
      <FinanceSection index={next()} report={report} />
      <ComparisonSection index={next()} report={report} />
      <Section index={next()} title="Рекомендации по удержанию студентов" hint="Только по данным этого отчёта">
        <Bullets items={report.recommendations} empty="Данных для рекомендаций недостаточно." />
      </Section>

      <Section index={next()} title="Итоги месяца">
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
        <ManagementSummary report={report} />
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
  // Departure filters live in the URL, so the page, a refresh and the PDF all see the same ones.
  const filters: Partial<ReportFilters> = {
    ...(params.get('group') ? { group: Number(params.get('group')) } : {}),
    ...(params.get('teacher') ? { teacher: Number(params.get('teacher')) } : {}),
    ...(params.get('reason') ? { reason: params.get('reason') as string } : {}),
  }
  const setFilter = (key: keyof ReportFilters, value: string) => {
    const nextParams = new URLSearchParams(params)
    if (value) nextParams.set(key, value)
    else nextParams.delete(key)
    setParams(nextParams, { replace: true })
  }
  const { data: options } = useAssistantOptions()
  const { data, isPending, isFetching, isError, error, refetch } = useMonthlyReport(year, month, filters)

  const years = Array.from({ length: now.getFullYear() - FIRST_YEAR + 1 }, (_, i) => now.getFullYear() - i)
  const maxMonth = draft.year === now.getFullYear() ? now.getMonth() + 1 : 12
  const generate = () => {
    const next = { year: draft.year, month: Math.min(draft.month, maxMonth) }
    if (next.year === year && next.month === month) void refetch()
    else {
      const nextParams = new URLSearchParams(params)
      nextParams.set('year', String(next.year))
      nextParams.set('month', String(next.month))
      setParams(nextParams, { replace: true })
    }
  }
  const message = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail
  const { showToast } = useToast()
  const [downloading, setDownloading] = useState(false)
  // The PDF is always the report on screen: its own year and month, never the picker's draft.
  const downloadPdf = async () => {
    if (!data) return
    setDownloading(true)
    try {
      await assistantApi.downloadMonthlyReportPdf(data.year, data.month, filters)
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
          <Report report={data} filterBar={
            <div className="flex flex-wrap gap-2" aria-label="Фильтры уходов">
              <div className="w-full sm:w-44"><Select aria-label="Группа" value={String(filters.group ?? '')} placeholder="Все группы"
                onChange={(e) => setFilter('group', e.target.value)}
                options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} /></div>
              <div className="w-full sm:w-48"><Select aria-label="Тренер" value={String(filters.teacher ?? '')} placeholder="Все тренеры"
                onChange={(e) => setFilter('teacher', e.target.value)}
                options={(options?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))} /></div>
              <div className="w-full sm:w-56"><Select aria-label="Причина ухода" value={filters.reason ?? ''} placeholder="Все причины"
                onChange={(e) => setFilter('reason', e.target.value)}
                options={[...(options?.deactivation_reasons ?? []), { value: 'unknown', label: 'Не указана' }]} /></div>
            </div>
          } />
          <p className="mt-8 flex items-center gap-1.5 border-t border-border pt-3 text-xs text-ink-muted">
            <Eye className="size-3.5" aria-hidden />
            Только просмотр: отчёт считается из посещаемости, ДЗ, истории статусов, опросов и стипендий и ничего не меняет. KPI тренеров — в отчёте Team Lead.
          </p>
        </>
      ) : null}
    </div>
  )
}

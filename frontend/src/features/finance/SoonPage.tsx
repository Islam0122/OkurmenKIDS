import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { DataTable } from '@/components/ui/DataTable'
import type { DataTableColumn } from '@/components/ui/DataTable'
import { Pagination } from '@/components/ui/Pagination'
import type { QueueRow, SoonQueuePage, SoonSection, UpcomingObligation } from '@/types/finance'
import { cn } from '@/utils/cn'

import { QueueRowActions, StudentCell } from './QueuePage'
import {
  Amount,
  ContactModal,
  FINANCE_KEY,
  ListFilters,
  Loadable,
  MonthProgress,
  formatDate,
  rowProgress,
  som,
  useFinanceMe,
  useFinanceOptions,
  useUrlFilters,
} from './ui'

const PAGE_SIZE = 25
const DEFAULT_SECTION: SoonSection = 'days_1_3'

export const SOON_SECTIONS: { key: SoonSection; label: string; empty: string }[] = [
  { key: 'days_1_3', label: 'Через 1–3 дня', empty: 'В ближайшие 1–3 дня оплат нет' },
  { key: 'days_4_5', label: 'Через 4–5 дней', empty: 'Через 4–5 дней оплат нет' },
  { key: 'days_6_10', label: 'Через 6–10 дней', empty: 'Через 6–10 дней оплат нет' },
  { key: 'next_month', label: 'Следующий месяц', empty: 'В следующем месяце (позже 10 дней) оплат нет' },
  { key: 'paid_course', label: 'Полностью оплатили курс', empty: 'Нет студентов с полностью оплаченным курсом' },
]

const LABEL = Object.fromEntries(SOON_SECTIONS.map((s) => [s.key, s.label])) as Record<SoonSection, string>

const ORDERINGS = [
  { value: 'date', label: 'Ближайший срок' }, { value: 'name', label: 'По имени' }, { value: 'group', label: 'По группе' },
]

function daysText(days: number): string {
  const n = Math.abs(days) % 100
  const last = n % 10
  const word = n > 10 && n < 20 ? 'дней' : last === 1 ? 'день' : last >= 2 && last <= 4 ? 'дня' : 'дней'
  return days === 1 ? 'завтра' : `через ${days} ${word}`
}

function obligationTitle(o: UpcomingObligation): string {
  const what = o.kind === 'COURSE' ? 'Весь курс' : o.kind === 'PACKAGE' ? `Пакет №${o.month_number}` : `Месяц ${o.month_number}`
  return o.number ? `${what} · ${o.number}` : what
}

/** Одно обязательство: сумма к оплате, аванс, срок и откуда известна дата. */
function ObligationLine({ o, muted }: { o: UpcomingObligation; muted?: boolean }) {
  const prepaid = Number(o.paid) > 0
  const credit = Number(o.credit_applied) > 0
  return (
    <div className={cn('text-sm', muted && 'text-ink-secondary')}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className={cn('whitespace-nowrap font-semibold tabular-nums', !muted && 'text-brand-700')}>{som(o.to_pay)}</span>
        <span>{obligationTitle(o)}</span>
        <Badge tone={o.source === 'invoice' ? 'info' : 'muted'}>{o.source === 'invoice' ? 'Выставлено' : 'Ещё не выставлено'}</Badge>
        {muted ? <span className="text-xs">{LABEL[o.section]}</span> : null}
      </div>
      <p className="text-xs text-ink-secondary">
        Срок {formatDate(o.due_date)} ({daysText(o.days)})
        {o.date_basis === 'schedule' && o.due_lesson ? ` · ${o.due_lesson}-й урок месяца по расписанию группы` : ''}
        {o.date_basis === 'schedule' && !o.due_lesson ? ' · по расписанию группы' : ''}
        {credit ? ` · аванс закрывает ${som(o.credit_applied)} из ${som(o.balance)}` : ''}
        {prepaid ? ` · оплачено ранее ${som(o.paid)}` : ''}
      </p>
    </div>
  )
}

function CourseState({ row }: { row: QueueRow }) {
  const course = row.course_payment
  if (!course) return <span className="text-sm text-ink-secondary">Тариф без курса</span>
  if (course.paid_in_full) return <Badge tone="success">Курс оплачен</Badge>
  return (
    <div className="text-sm">
      <p className="whitespace-nowrap">Осталось по курсу <span className="font-semibold tabular-nums">{som(course.unpaid)}</span></p>
      <p className="text-xs text-ink-secondary">из {som(course.final_course_price)}</p>
    </div>
  )
}

function DebtCell({ row }: { row: QueueRow }) {
  const overdue = Number(row.overdue_amount) > 0
  return (
    <div className="text-sm">
      <Amount value={row.due_now} tone={Number(row.due_now) > 0 ? 'brand' : 'muted'} />
      {overdue ? <p className="text-xs text-danger">в т.ч. просрочено {som(row.overdue_amount)}</p> : null}
      {Number(row.credit) > 0 ? <p className="text-xs text-ink-secondary">аванс {som(row.credit)}</p> : null}
    </div>
  )
}

function SectionCards({ data, value, onChange }: {
  data?: SoonQueuePage
  value: SoonSection
  onChange: (key: SoonSection) => void
}) {
  return (
    <div role="tablist" aria-label="Подразделы «Скоро оплата»" className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {SOON_SECTIONS.map((s) => {
        const summary = data?.sections[s.key]
        const active = value === s.key
        return (
          <button key={s.key} type="button" role="tab" aria-selected={active} onClick={() => onChange(s.key)}
            className={cn('card p-4 text-left transition-colors', active ? 'ring-2 ring-brand-500' : 'hover:bg-surface-hover')}>
            <p className="text-xs font-medium uppercase tracking-wide text-ink-secondary">{s.label}</p>
            <p className={cn('mt-1 text-xl font-semibold tabular-nums text-ink', active && 'text-brand-700')}>
              {summary ? summary.count : '—'}
              <span className="ml-1 text-sm font-normal text-ink-secondary">студ.</span>
            </p>
            <p className="mt-1 text-xs text-ink-secondary">
              {s.key === 'paid_course' ? 'к оплате 0 сом' : `к оплате ${summary ? som(summary.amount) : '—'}`}
            </p>
          </button>
        )
      })}
    </div>
  )
}

export function SoonPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const me = useFinanceMe()
  const options = useFinanceOptions()
  const [filters, setFilters] = useUrlFilters()
  const [contact, setContact] = useState<QueueRow | null>(null)
  const section = filters.section ?? DEFAULT_SECTION
  const query = useQuery({
    queryKey: [...FINANCE_KEY, 'queue', 'soon', { ...filters, section }],
    queryFn: () => financeApi.soon({ ...filters, section, page_size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  })
  const canPay = me.data?.can_record_payments ?? false
  const open = (row: QueueRow) => navigate(`/finance/students/${row.profile}`, { state: { from: location.pathname + location.search } })
  const meta = SOON_SECTIONS.find((s) => s.key === section) ?? SOON_SECTIONS[0]
  const paidCourse = section === 'paid_course'

  const mine = (r: QueueRow) => (r.upcoming ?? []).filter((o) => o.section === section)
  const others = (r: QueueRow) => (r.upcoming ?? []).filter((o) => o.section !== section)

  const columns: DataTableColumn<QueueRow>[] = paidCourse ? [
    { key: 'student', header: 'Студент', render: (r) => <StudentCell row={r} /> },
    { key: 'package', header: 'Финансовый пакет', render: (r) => <MonthProgress {...rowProgress(r)} /> },
    { key: 'price', header: 'Стоимость курса', render: (r) => (
      <div className="text-sm"><Amount value={r.course_payment?.final_course_price} />
        {Number(r.discount_amount) > 0 ? <p className="text-xs text-ink-secondary">скидка {som(r.discount_amount)}</p> : null}</div>
    ) },
    { key: 'paid', header: 'Внесено', render: (r) => (
      <div className="text-sm"><Amount value={r.course_payment?.allocated} tone="muted" />
        {Number(r.course_payment?.credit) > 0 ? <p className="text-xs text-ink-secondary">+ аванс {som(r.course_payment?.credit)}</p> : null}
        {Number(r.course_payment?.adjusted) > 0 ? <p className="text-xs text-ink-secondary">+ корректировки {som(r.course_payment?.adjusted)}</p> : null}</div>
    ) },
    { key: 'state', header: 'К оплате', render: (r) => (
      <div className="space-y-1"><Amount value="0" tone="muted" /><div><CourseState row={r} /></div></div>
    ) },
    { key: 'actions', header: '', className: 'text-right',
      render: (r) => <QueueRowActions row={r} canPay={canPay} invoice={null} onContact={setContact} onOpen={open} /> },
  ] : [
    { key: 'student', header: 'Студент', render: (r) => <StudentCell row={r} /> },
    { key: 'package', header: 'Финансовый пакет', render: (r) => <MonthProgress {...rowProgress(r)} /> },
    { key: 'date', header: 'Ближайшая оплата', render: (r) => (
      <div className="text-sm"><p className="whitespace-nowrap font-medium">{formatDate(r.section_due_date)}</p>
        <p className="text-xs text-ink-secondary">{r.section_days != null ? daysText(r.section_days) : '—'}</p></div>
    ) },
    { key: 'payment', header: 'Предстоящий платёж', render: (r) => (
      <div className="min-w-56 space-y-2">
        {mine(r).map((o) => <ObligationLine key={o.key} o={o} />)}
        {others(r).map((o) => <ObligationLine key={o.key} o={o} muted />)}
      </div>
    ) },
    { key: 'debt', header: 'К оплате сейчас', render: (r) => <DebtCell row={r} /> },
    { key: 'course', header: 'Курс', render: (r) => <CourseState row={r} /> },
    { key: 'actions', header: '', className: 'text-right',
      render: (r) => <QueueRowActions row={r} canPay={canPay} invoice={mine(r).find((o) => o.invoice)?.invoice ?? null}
        onContact={setContact} onOpen={open} /> },
  ]

  return (
    <div>
      <PageHeader title="Скоро оплата"
        description="Предстоящие платежи по дате срока (Asia/Bishkek, календарные дни). Срок сегодня — в «К оплате», прошедший — в «Просроченные». Дата урока-срока — по расписанию группы."
        badge={query.data ? <span className="rounded-full bg-surface-hover px-2.5 py-1 text-sm text-ink-secondary">{query.data.count}</span> : undefined} />
      <SectionCards data={query.data} value={section} onChange={(key) => setFilters({ ...filters, section: key, page: 1 })} />
      <ListFilters filters={filters} onChange={(f) => setFilters({ ...f, section })} options={options.data}
        orderings={paidCourse ? ORDERINGS.slice(1) : ORDERINGS} />
      {query.data && query.data.undated > 0 && !paidCourse ? (
        <p className="mt-3 text-xs text-ink-secondary">
          У {query.data.undated} студ. дата срока не подтверждена (нет расписания группы вперёд или ученик не обучается) — в подразделы они не включены.
        </p>
      ) : null}
      <div className="mt-4">
        <Loadable query={query} empty={(d) => d.count === 0} emptyTitle={meta.empty}
          emptyDescription={filters.search || filters.group || filters.program ? 'Попробуйте изменить фильтры.' : undefined}>
          {(data) => (
            <>
              <DataTable columns={columns} rows={data.results} getRowKey={(r) => r.profile} onRowClick={open} />
              <div className="mt-3">
                <Pagination page={data.page} pageSize={data.page_size} totalCount={data.count}
                  onPageChange={(page) => setFilters({ ...filters, section, page })} />
              </div>
            </>
          )}
        </Loadable>
      </div>
      {contact ? <ContactModal profile={contact.profile} student={contact.student_name} onClose={() => setContact(null)} /> : null}
    </div>
  )
}

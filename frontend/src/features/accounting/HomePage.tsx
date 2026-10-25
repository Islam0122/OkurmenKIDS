import { useQuery } from '@tanstack/react-query'
import { ArrowLeftRight, ChevronRight, LineChart, ReceiptText, Settings2, Users, Wallet } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { FINANCE_KEY, useFinanceMe } from '@/features/finance/ui'
import { useFinanceOverview } from '@/hooks/useAccounting'
import type { QueueCounts } from '@/types/finance'

import { currentMonthKey } from './financeShared'
import { som } from './shared'

interface SubLink {
  to: string
  label: string
  hint?: string
  count?: number
  tone?: 'warning' | 'danger' | 'info'
}

const COUNT_TONE = { warning: 'warning', danger: 'danger', info: 'info' } as const

function SectionCard({ icon: Icon, title, description, figures, links }: {
  icon: LucideIcon
  title: string
  description: string
  figures?: ReactNode
  links: SubLink[]
}) {
  return (
    <section className="card card-body flex min-w-0 flex-col" aria-labelledby={`sec-${title}`}>
      <div className="mb-3 flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 id={`sec-${title}`} className="text-base font-semibold text-ink">{title}</h2>
          <p className="text-sm text-ink-secondary">{description}</p>
        </div>
      </div>
      {figures ? <dl className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3">{figures}</dl> : null}
      <ul className="-mx-2 mt-auto divide-y divide-border">
        {links.map((link) => (
          <li key={link.to + link.label}>
            <Link to={link.to} className="flex items-center gap-2 rounded-lg px-2 py-2 text-sm hover:bg-surface-hover">
              <span className="min-w-0 flex-1">
                <span className="font-medium text-ink">{link.label}</span>
                {link.hint ? <span className="block text-xs text-ink-secondary">{link.hint}</span> : null}
              </span>
              {link.count ? <Badge tone={COUNT_TONE[link.tone ?? 'info']}>{link.count}</Badge> : null}
              <ChevronRight className="size-4 shrink-0 text-ink-muted" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Figure({ label, value, tone }: { label: string; value: string; tone?: 'warning' | 'danger' }) {
  return (
    <div className="min-w-0 rounded-lg bg-surface-muted px-3 py-2">
      <dt className="truncate text-xs text-ink-secondary">{label}</dt>
      <dd className={tone === 'danger' ? 'font-semibold tabular-nums text-danger' : tone === 'warning'
        ? 'font-semibold tabular-nums text-warning' : 'font-semibold tabular-nums text-ink'}>{value}</dd>
    </div>
  )
}

/**
 * Обзор бухгалтерии: четыре основных раздела (оплата студентов, зарплата,
 * расходы, аналитика) и вспомогательные (касса, настройки). Цифры — текущего
 * месяца из единой финансовой панели, счётчики очередей — из оплаты обучения.
 */
export function AccountingHomePage() {
  const overview = useFinanceOverview({ month: currentMonthKey() })
  const me = useFinanceMe()
  const counts = useQuery<QueueCounts>({
    queryKey: [...FINANCE_KEY, 'counts'], queryFn: financeApi.counts, enabled: me.data?.can_view_money ?? false,
  })
  const d = overview.data
  const c = counts.data
  const dash = (value: string | undefined) => (d ? som(value) : '…')

  return (
    <div>
      <PageHeader
        title="Бухгалтерия"
        description="Выберите раздел для задачи. Цифры — за текущий месяц; поступления, начисления, авансы, расходы, начисленная и выплаченная зарплата считаются отдельно и не смешиваются."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard
          icon={ReceiptText}
          title="1. Оплата студентов"
          description="Договоры, начисления, платежи, авансы, долги и возвраты."
          figures={<>
            <Figure label="Поступило за месяц" value={dash(d?.students.net)} />
            <Figure label="Долг сейчас" value={dash(d?.students.debt_now)} tone={Number(d?.students.debt_now) > 0 ? 'warning' : undefined} />
            <Figure label="Просрочено" value={dash(d?.students.overdue_now)} tone={Number(d?.students.overdue_now) > 0 ? 'danger' : undefined} />
          </>}
          links={[
            { to: '/finance/students', label: 'Все студенты и финансовые карточки' },
            { to: '/finance/soon', label: 'Скоро оплата', hint: 'через 1–3, 4–5, 6–10 дней, в следующем месяце', count: c?.soon, tone: 'warning' },
            { to: '/finance/to-pay', label: 'К оплате', count: c?.to_pay, tone: 'info' },
            { to: '/finance/overdue', label: 'Просроченные платежи', count: c?.overdue, tone: 'danger' },
            { to: '/finance/payments', label: 'История платежей', hint: 'по дате фактического поступления, чеки' },
            { to: '/finance/prepayments', label: 'Авансы и распределение авансов',
              hint: d ? `остаток предоплаты ${som(d.students.prepayment)}, не распределено ${som(d.students.unallocated_credit)}` : undefined },
            { to: '/finance/payments?kind=refund', label: 'Возвраты' },
            { to: '/finance/payments?status=void', label: 'Сторнирования' },
            { to: '/finance/plans', label: 'Договоры и тарифы', hint: 'тарифы программ; договор — в карточке студента' },
            { to: '/finance/analytics', label: 'Статистика оплат и задолженностей' },
            { to: '/finance/soon?section=paid_course', label: 'Полностью оплаченные курсы',
              hint: 'вся стоимость курса с учётом скидок, возвратов и корректировок' },
          ]}
        />

        <SectionCard
          icon={Users}
          title="2. Зарплата сотрудников"
          description="Начисление и фактическая выплата — раздельно; оценки незавершённых блоков — не начисление."
          figures={<>
            <Figure label="Начислено за месяц" value={dash(d?.payroll.accrued)} />
            <Figure label="Выплачено в месяце" value={dash(d?.payroll.paid_cash)} />
            <Figure label="Остаток к выплате" value={dash(d?.payroll.outstanding_now)} tone={Number(d?.payroll.outstanding_now) > 0 ? 'warning' : undefined} />
          </>}
          links={[
            { to: '/accounting/payroll', label: 'Начисления и выплаты', hint: 'преподаватели (процент за блок) и администрация (оклад)' },
            { to: '/accounting/earnings', label: 'Начисления за проведённые занятия', hint: 'заработок по урокам и блокам на сегодня' },
            { to: '/accounting/courses', label: 'Курсы и блоки', hint: 'проведённые уроки, циклы, начисления за блок' },
            { to: '/accounting/payout-plan', label: 'План выплат', hint: 'начислено, выплачено, остаток к выплате' },
            { to: '/accounting/settings', label: 'Ставки, оклады, налоги и удержания' },
            { to: '/accounting/reports', label: 'Отчёт по сотрудникам и месяцам' },
            { to: '/accounting/analytics', label: 'Аналитика по направлениям', hint: 'IT, English, Soft Skills, тимлиды, ассистенты, персонал' },
          ]}
        />

        <SectionCard
          icon={Wallet}
          title="3. Расходы компании"
          description="Неоплаченный расход — обязательство, а не потраченные деньги."
          figures={<>
            <Figure label="Оплачено за месяц" value={dash(d?.expenses.paid)} />
            <Figure label="Не оплачено" value={dash(d?.expenses.unpaid_now_amount)} tone={Number(d?.expenses.unpaid_now_amount) > 0 ? 'warning' : undefined} />
            <Figure label="Просрочено" value={dash(d?.expenses.unpaid_now_overdue_amount)} tone={Number(d?.expenses.unpaid_now_overdue_amount) > 0 ? 'danger' : undefined} />
          </>}
          links={[
            { to: '/accounting/expenses', label: 'Все расходы', hint: 'создание, оплата, документы, история' },
            { to: '/accounting/expenses?status=UNPAID', label: 'К оплате поставщикам', count: d?.expenses.unpaid_now_count, tone: 'warning' },
            { to: '/accounting/expenses?tab=recurring', label: 'Регулярные расходы', hint: 'аренда, интернет, связь — раз в месяц' },
            { to: '/accounting/expenses?tab=report', label: 'Отчёт по категориям и периодам' },
            { to: '/accounting/expenses?tab=categories', label: 'Категории расходов' },
          ]}
        />

        <SectionCard
          icon={LineChart}
          title="4. Аналитика и отчёты"
          description="Единая панель за период со сравнением с прошлым периодом и выгрузкой в Excel."
          figures={<>
            <Figure label="Приход за месяц" value={dash(d?.cash_flow.inflow)} />
            <Figure label="Расход за месяц" value={dash(d?.cash_flow.outflow)} />
            <Figure label="Денежный поток" value={dash(d?.cash_flow.net)} tone={Number(d?.cash_flow.net) < 0 ? 'danger' : undefined} />
          </>}
          links={[
            { to: '/accounting/finance', label: 'Финансовая панель', hint: 'поступления, долги, зарплата, расходы, авансы, поток' },
            { to: '/finance/analytics', label: 'Отчёт по платежам и долгам студентов' },
            { to: '/accounting/reports', label: 'Отчёт по зарплате' },
            { to: '/accounting/expenses?tab=report', label: 'Отчёт по расходам и категориям' },
            { to: '/accounting/cash', label: 'Отчёт по движению денежных средств' },
          ]}
        />

        <SectionCard
          icon={ArrowLeftRight}
          title="Касса и движение денег"
          description="Все фактические поступления и выплаты одной лентой, сальдо по способам оплаты."
          links={[{ to: '/accounting/cash', label: 'Движение денежных средств' }]}
        />

        <SectionCard
          icon={Settings2}
          title="Финансовые настройки"
          description="Правила, тарифы и журнал изменений. Изменения сохраняются в истории с причиной."
          links={[
            { to: '/accounting/settings', label: 'Зарплатные правила, налоги и удержания' },
            { to: '/accounting/pricing', label: 'Стоимость курсов (база процента тренера)' },
            { to: '/finance/settings', label: 'Настройки оплаты обучения', hint: 'скидки, сроки, лимит возврата, реквизиты чека' },
            { to: '/accounting/expenses?tab=categories', label: 'Категории расходов' },
            { to: '/accounting/audit', label: 'Журнал изменений' },
          ]}
        />
      </div>
    </div>
  )
}

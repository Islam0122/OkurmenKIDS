import { ArrowRight, BarChart3, LogOut, ReceiptText, Users, Wallet } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { useAuth } from '@/hooks/useAuth'

interface SectionCard {
  to: string
  title: string
  description: string
  icon: LucideIcon
}

/** Четыре основных раздела бухгалтерии — существующие страницы. */
export const HOME_SECTIONS: SectionCard[] = [
  { to: '/finance', title: 'Оплата студентов', description: 'Договоры, платежи, долги и авансы', icon: Wallet },
  { to: '/accounting/payroll', title: 'Зарплата сотрудников', description: 'Начисления, выплаты и остатки', icon: Users },
  { to: '/accounting/expenses', title: 'Расходы компании', description: 'Учёт расходов по категориям', icon: ReceiptText },
  { to: '/accounting/finance', title: 'Аналитика и отчёты', description: 'Финансовая панель и отчёты', icon: BarChart3 },
]

/**
 * Главная бухгалтерии — без sidebar: логотип, заголовок и четыре карточки
 * разделов. Внутренние страницы разделов открываются в обычном layout
 * бухгалтерии со своим меню.
 */
export function AccountingHomePage() {
  const { logout } = useAuth()
  return (
    <div className="relative flex min-h-dvh flex-col items-center bg-surface-muted px-4 py-10 sm:px-6 sm:py-16">
      <button type="button" onClick={logout}
        className="absolute right-4 top-4 flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-ink-secondary transition-colors hover:bg-surface-hover hover:text-danger sm:right-6">
        <LogOut className="size-4" aria-hidden />
        Выйти
      </button>

      <header className="mb-10 flex flex-col items-center text-center sm:mb-12">
        <img src={logo} alt="Okurmen Kids" className="mb-4 size-16 object-contain sm:size-20" />
        <h1 className="text-2xl font-semibold text-ink sm:text-3xl">Бухгалтерия</h1>
        <p className="mt-2 text-sm text-ink-secondary sm:text-base">Финансовое управление Okurmen Kids</p>
      </header>

      <nav aria-label="Разделы бухгалтерии" className="w-full max-w-3xl">
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-5">
          {HOME_SECTIONS.map(({ to, title, description, icon: Icon }) => (
            <li key={to}>
              <Link to={to}
                className="group flex h-full items-center gap-4 rounded-2xl border border-border bg-surface p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 sm:p-6">
                <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 transition-colors group-hover:bg-brand-500 group-hover:text-white sm:size-14">
                  <Icon className="size-6 sm:size-7" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-base font-semibold text-ink sm:text-lg">{title}</span>
                  <span className="mt-0.5 block text-sm text-ink-secondary">{description}</span>
                </span>
                <ArrowRight className="size-5 shrink-0 text-ink-muted transition-all group-hover:translate-x-1 group-hover:text-brand-600" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  )
}

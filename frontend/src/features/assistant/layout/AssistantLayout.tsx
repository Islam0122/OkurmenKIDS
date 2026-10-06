import { Suspense, useEffect, useState } from 'react'
import { LogOut, Menu, Search } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { Drawer } from '@/components/ui/Drawer'
import { LoadingState } from '@/components/ui/LoadingState'
import { useAuth } from '@/hooks/useAuth'
import { ROLE_LABEL } from '@/lib/roles'
import { cn } from '@/utils/cn'

import { AssistantActionsProvider } from '../actions/AssistantActions'
import { ASSISTANT_MOBILE_PRIMARY, ASSISTANT_PROFILE, ASSISTANT_SECTIONS } from './assistantNav'
import type { AssistantNavItem } from './assistantNav'
import { CommandPalette } from './CommandPalette'
import { CreateMenu } from './CreateMenu'

const ROW = 'flex h-9 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors'

function NavRow({ item, onNavigate }: { item: AssistantNavItem; onNavigate?: () => void }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) => cn(ROW, isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink')}
    >
      <item.icon className="size-[18px] shrink-0" aria-hidden />
      <span className="truncate">{item.label}</span>
    </NavLink>
  )
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const { logout } = useAuth()
  return (
    <div className="flex h-full flex-col">
      <nav className="flex-1 overflow-y-auto px-3 py-3" aria-label="Навигация ассистента">
        {ASSISTANT_SECTIONS.map((section) => (
          <div key={section.title ?? 'main'} className={section.title ? 'mt-4' : undefined}>
            {section.title ? <p className="mb-1 px-3 text-2xs font-semibold tracking-wider text-ink-muted uppercase">{section.title}</p> : null}
            <div className="space-y-0.5">
              {section.items.map((item) => <NavRow key={item.to} item={item} onNavigate={onNavigate} />)}
            </div>
          </div>
        ))}
      </nav>
      <div className="space-y-0.5 border-t border-border px-3 py-3">
        <NavRow item={ASSISTANT_PROFILE} onNavigate={onNavigate} />
        <button type="button" onClick={logout} className={cn(ROW, 'w-full text-ink-secondary hover:bg-surface-hover hover:text-danger')}>
          <LogOut className="size-[18px] shrink-0" aria-hidden />
          Выйти
        </button>
      </div>
    </div>
  )
}

/**
 * The Assistant Workspace shell — the same chrome as the LMS (AppLayout):
 * a 240px sidebar, a 64px sticky header, a 1280px page container and the
 * phone bottom bar; plus the global «+ Создать» in the header.
 */
export function AssistantLayout() {
  const { user } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSearchOpen(true)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])
  const initials = user ? `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase() : ''

  return (
    <AssistantActionsProvider>
      <div className="flex min-h-dvh bg-surface-muted">
        <aside className="sticky top-0 hidden h-dvh w-sidebar shrink-0 flex-col border-r border-border bg-surface lg:flex">
          <div className="flex h-header shrink-0 items-center gap-2.5 border-b border-border px-6">
            <img src={logo} alt="OkurmenKIDS" className="size-8 shrink-0 object-contain" />
            <span className="font-semibold text-ink">OkurmenKIDS</span>
          </div>
          <div className="min-h-0 flex-1">
            <NavList />
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-header shrink-0 items-center justify-between gap-3 border-b border-border bg-surface px-4 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-2 lg:hidden">
              <img src={logo} alt="OkurmenKIDS" className="size-8 shrink-0 object-contain" />
              <span className="hidden truncate font-semibold text-ink min-[420px]:inline">OkurmenKIDS</span>
            </div>
            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              className="hidden h-9 w-full max-w-sm items-center gap-2 rounded-lg border border-border bg-surface-muted px-3 text-sm text-ink-muted hover:border-border-strong md:flex"
            >
              <Search className="size-4 shrink-0" aria-hidden />
              <span className="flex-1 truncate text-left">Поиск: студенты, группы, тренеры…</span>
              <kbd className="rounded border border-border bg-surface px-1.5 text-2xs font-medium text-ink-secondary">Ctrl K</kbd>
            </button>
            <div className="flex shrink-0 items-center gap-2">
              <button type="button" onClick={() => setSearchOpen(true)} aria-label="Поиск"
                className="flex size-9 items-center justify-center rounded-lg text-ink-secondary hover:bg-surface-hover md:hidden">
                <Search className="size-5" aria-hidden />
              </button>
              <CreateMenu />
              <button
                type="button"
                onClick={() => setMenuOpen(true)}
                className="flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-ink-secondary hover:bg-surface-hover lg:hidden"
              >
                <Menu className="size-5" aria-hidden />
                <span className="hidden sm:inline">Меню</span>
              </button>
              <div className="hidden items-center gap-2 sm:flex">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">
                  {initials}
                </span>
                <div className="max-w-48 leading-tight">
                  <p className="truncate text-sm font-medium text-ink">{user?.first_name} {user?.last_name}</p>
                  <p className="text-xs text-ink-secondary">{user ? ROLE_LABEL[user.role] : ''}</p>
                </div>
              </div>
            </div>
          </header>

          <main className="flex-1 pb-[calc(var(--spacing-mobile-nav)+env(safe-area-inset-bottom)+1.5rem)] lg:pb-8">
            <div className="mx-auto w-full max-w-page px-4 pt-6 sm:px-6 lg:px-8">
              <Suspense fallback={<LoadingState label="Загрузка страницы…" />}>
                <Outlet />
              </Suspense>
            </div>
          </main>
        </div>

        <nav
          aria-label="Основная навигация"
          className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
        >
          <div className="grid h-mobile-nav grid-cols-5">
            {ASSISTANT_MOBILE_PRIMARY.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn('flex min-w-0 flex-col items-center justify-center gap-1 text-2xs font-medium', isActive ? 'text-brand-600' : 'text-ink-muted hover:text-ink')
                }
              >
                <item.icon className="size-5 shrink-0" aria-hidden />
                <span className="max-w-full truncate">{item.label}</span>
              </NavLink>
            ))}
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              className="flex min-w-0 flex-col items-center justify-center gap-1 text-2xs font-medium text-ink-muted hover:text-ink"
            >
              <Menu className="size-5 shrink-0" aria-hidden />
              <span>Ещё</span>
            </button>
          </div>
        </nav>

        <CommandPalette isOpen={searchOpen} onClose={() => setSearchOpen(false)} />
        <Drawer isOpen={menuOpen} onClose={() => setMenuOpen(false)} title="Меню" side="left">
          <div className="-m-4 h-[calc(100%+2rem)] sm:-m-5 sm:h-[calc(100%+2.5rem)]">
            <NavList onNavigate={() => setMenuOpen(false)} />
          </div>
        </Drawer>
      </div>
    </AssistantActionsProvider>
  )
}

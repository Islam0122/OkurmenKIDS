import '@fontsource-variable/manrope'

import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { ChevronDown, CircleHelp, Globe, Info, LogIn, LogOut } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { useAuth } from '@/hooks/useAuth'
import { ROLE_LABEL } from '@/lib/roles'
import type { User } from '@/types/auth'
import { cn } from '@/utils/cn'

import { PORTAL_PATH } from './config'
import { LANGS, LanguageProvider, useI18n, type Lang } from './i18n'
import { InfoModals, type InfoModalId } from './InfoModals'

const focusRing = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pd-green'

/** White full-screen frame shared by the launcher and the programs page: header, footer, dialogs. */
export function PortalShell({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <Frame>{children}</Frame>
    </LanguageProvider>
  )
}

function Frame({ children }: { children: ReactNode }) {
  const [modal, setModal] = useState<InfoModalId | null>(null)
  const close = useCallback(() => setModal(null), [])

  useEffect(() => {
    const previous = document.title
    document.title = 'Okurmen Digital'
    return () => {
      document.title = previous
    }
  }, [])

  return (
    <div className="relative isolate flex min-h-dvh flex-col overflow-x-hidden bg-pd-bg font-display text-pd-ink antialiased selection:bg-pd-green/20">
      <div aria-hidden className="pd-grid pointer-events-none fixed inset-0 -z-10" />
      <div
        aria-hidden
        className="pointer-events-none fixed left-1/2 top-[-20rem] -z-10 h-[32rem] w-[56rem] max-w-[140vw] -translate-x-1/2 rounded-full bg-pd-green/[0.07] blur-3xl"
      />
      <PortalHeader onOpen={setModal} />
      {children}
      <PortalFooter onOpen={setModal} />
      <InfoModals open={modal} onClose={close} />
    </div>
  )
}

function PortalHeader({ onOpen }: { onOpen: (id: InfoModalId) => void }) {
  const { user, status, logout } = useAuth()
  const { t } = useI18n()
  const location = useLocation()

  return (
    <header className="relative z-30">
      <div className="mx-auto flex h-14 w-full max-w-[1100px] items-center justify-between gap-2 px-4 sm:h-16 sm:px-6">
        <Link to={PORTAL_PATH} aria-label={t.brand.home} className={cn('group flex min-w-0 items-center gap-2 rounded-lg sm:gap-2.5', focusRing)}>
          <span className="grid size-8 shrink-0 place-items-center rounded-xl border border-pd-line bg-pd-panel pd-shadow sm:size-9 transition-colors group-hover:border-pd-green-line">
            <img src={logo} alt="" className="size-6 object-contain" />
          </span>
          <span className="min-w-0 leading-tight">
            <span className="block truncate text-xs font-extrabold tracking-[0.04em] min-[400px]:tracking-[0.12em] sm:text-sm">
              OKURMEN <span className="text-pd-green">DIGITAL</span>
            </span>
            <span className="hidden truncate text-[10px] font-semibold uppercase tracking-[0.2em] text-pd-faint min-[400px]:block">{t.brand.subtitle}</span>
          </span>
        </Link>

        <nav className="flex shrink-0 items-center gap-0.5 sm:gap-1.5" aria-label="Okurmen Digital">
          <LanguageSelect />
          <HeaderButton icon={Info} label={t.nav.about} onClick={() => onOpen('about')} />
          <HeaderButton icon={CircleHelp} label={t.nav.help} onClick={() => onOpen('help')} />
          <span className="mx-0.5 hidden h-5 w-px bg-pd-line sm:block" aria-hidden />
          {status === 'authenticated' && user ? (
            <UserChip user={user} onLogout={logout} logoutLabel={t.nav.logout} />
          ) : status === 'loading' ? (
            <span className="h-9 w-9 animate-pulse rounded-lg bg-zinc-100 sm:w-24" aria-label={t.nav.checking} />
          ) : (
            <Link
              to="/login"
              state={{ from: { pathname: location.pathname, search: location.search } }}
              aria-label={t.nav.login}
              className={cn(
                'inline-flex h-9 items-center gap-2 rounded-lg bg-pd-ink px-2.5 text-sm font-semibold text-white pd-shadow transition hover:bg-zinc-800 active:scale-[0.98] sm:px-3.5',
                focusRing,
              )}
            >
              <LogIn className="size-4" aria-hidden />
              <span className="hidden sm:inline">{t.nav.login}</span>
            </Link>
          )}
        </nav>
      </div>
    </header>
  )
}

function HeaderButton({ icon: Icon, label, onClick }: { icon: typeof Info; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-haspopup="dialog"
      aria-label={label}
      title={label}
      className={cn(
        'inline-flex h-9 items-center gap-1.5 rounded-lg px-1.5 text-sm sm:px-2 font-medium text-pd-muted transition hover:bg-zinc-100 hover:text-pd-ink md:px-2.5',
        focusRing,
      )}
    >
      <Icon className="size-4" aria-hidden />
      <span className="hidden md:inline">{label}</span>
    </button>
  )
}

/** RU / KG / EN — a native select (keyboard, screen readers and phone pickers for free), styled. */
function LanguageSelect() {
  const { lang, setLang, t } = useI18n()
  return (
    <label className="relative inline-flex h-9 items-center rounded-lg border border-pd-line bg-pd-panel pd-shadow transition hover:border-pd-line-strong focus-within:border-pd-green focus-within:ring-2 focus-within:ring-pd-green/20">
      <span className="sr-only">{t.nav.language}</span>
      <Globe className="pointer-events-none absolute left-2.5 hidden size-3.5 text-pd-faint sm:block" aria-hidden />
      <select
        value={lang}
        onChange={(event) => setLang(event.target.value as Lang)}
        className="h-full cursor-pointer appearance-none rounded-lg bg-transparent pl-2.5 pr-6 sm:pl-7 text-xs font-semibold tracking-wide text-pd-ink outline-none"
      >
        {LANGS.map((item) => (
          <option key={item.id} value={item.id} aria-label={item.name}>
            {item.short}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 size-3 text-pd-faint" aria-hidden />
    </label>
  )
}

function initials(user: User): string {
  const value = `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.trim()
  return (value || user.username.charAt(0)).toUpperCase()
}

function UserChip({ user, onLogout, logoutLabel }: { user: User; onLogout: () => void; logoutLabel: string }) {
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username
  return (
    <div className="flex items-center gap-1 rounded-xl border border-pd-line bg-pd-panel p-1 pd-shadow">
      <span className="grid size-7 place-items-center rounded-lg bg-pd-green text-xs font-bold text-white" aria-hidden>
        {initials(user)}
      </span>
      <span className="hidden max-w-36 px-1.5 leading-tight lg:block">
        <span className="block truncate text-xs font-semibold">{name}</span>
        <span className="block truncate text-[11px] text-pd-faint">{ROLE_LABEL[user.role]}</span>
      </span>
      <span className="sr-only lg:hidden">{name}</span>
      <button
        type="button"
        onClick={onLogout}
        className={cn('grid size-7 place-items-center rounded-lg text-pd-faint transition hover:bg-zinc-100 hover:text-pd-ink', focusRing)}
        aria-label={logoutLabel}
        title={logoutLabel}
      >
        <LogOut className="size-4" aria-hidden />
      </button>
    </div>
  )
}

function PortalFooter({ onOpen }: { onOpen: (id: InfoModalId) => void }) {
  const { t } = useI18n()
  const link = cn('rounded text-pd-muted transition hover:text-pd-green', focusRing)
  return (
    <footer className="mt-auto border-t border-pd-line/80 bg-pd-bg/70 backdrop-blur-sm">
      <div className="mx-auto grid w-full max-w-[1100px] items-center gap-2 px-4 py-3 text-xs text-pd-faint sm:grid-cols-3 sm:px-6">
        <p className="text-center sm:text-left">{t.footer.copyright}</p>
        <div className="text-center leading-tight">
          <p className="font-semibold uppercase tracking-[0.16em] text-pd-muted">{t.footer.ecosystem}</p>
          <p className="mt-0.5 text-[11px]">{t.footer.credit}</p>
        </div>
        <nav aria-label={t.footer.links} className="flex items-center justify-center gap-2 sm:justify-end">
          <button type="button" className={link} onClick={() => onOpen('about')} aria-haspopup="dialog">
            {t.nav.about}
          </button>
          <span aria-hidden className="text-pd-line-strong">|</span>
          <button type="button" className={link} onClick={() => onOpen('help')} aria-haspopup="dialog">
            {t.nav.help}
          </button>
          <span aria-hidden className="text-pd-line-strong">|</span>
          <button type="button" className={link} onClick={() => onOpen('privacy')} aria-haspopup="dialog">
            {t.nav.privacy}
          </button>
        </nav>
      </div>
    </footer>
  )
}

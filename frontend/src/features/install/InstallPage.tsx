import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import {
  BookOpenCheck,
  CalendarDays,
  ChartColumn,
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Copy,
  Download,
  ExternalLink,
  Loader2,
  Lock,
  RefreshCw,
  Smartphone,
  UserRound,
  Wallet,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import { homeFor } from '@/lib/roles'
import { promptInstall } from '@/pwa/install'
import { registerInlineInstallButton, usePwaState } from '@/pwa/store'
import { cn } from '@/utils/cn'

import { currentDevice, desktopCanInstall, deviceLabel, installFlow, type DeviceInfo } from './detect'
import { AndroidScene, IosScene, SuccessBadge } from './Illustrations'
import { useInstallLang, type InstallLang, type InstallText } from './i18n'
import { QrCode } from './QrCode'

/**
 * /install — where the official QR code leads (public, no login).
 *
 * Detects the phone / computer and browser and shows only the steps for it:
 * iPhone & iPad Safari (animated Share → «На экран „Домой“» → «Добавить»),
 * other iOS browsers and in-app browsers (open in Safari / Chrome first),
 * Android (the browser's real install dialog via `beforeinstallprompt`, the
 * menu steps for Chrome, Samsung Internet, Firefox, Edge as a fallback) and
 * computers (Chromium / Safari, plus a QR code to install on the phone).
 * In the installed app (standalone) or after a successful install it shows
 * the «installed» screen. Nothing here signs anyone in or out.
 */

const RING = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600'
/** How long Chromium gets to offer its install dialog before the menu steps lead. */
const PROMPT_GRACE_MS = 3500

export function InstallPage() {
  const { lang, t, setLang } = useInstallLang()
  const device = useMemo(currentDevice, [])
  const flow = installFlow(device)
  const pwa = usePwaState()
  const [showSteps, setShowSteps] = useState(false)

  // The floating «install» card stays away: this whole page is the offer.
  useEffect(() => registerInlineInstallButton(), [])
  useEffect(() => {
    document.title = `${t.title} — OkurmenKids`
  }, [t.title])

  const installed = pwa.standalone || (pwa.installedHere && !pwa.promptEvent && !showSteps)

  return (
    <div className="min-h-dvh bg-white text-zinc-900">
      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-[420px] bg-[radial-gradient(60%_60%_at_50%_0%,rgba(16,185,129,0.12),transparent_70%)]" />
      <div className="relative mx-auto flex min-h-dvh max-w-5xl flex-col px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))] sm:px-6">
        <Header lang={lang} setLang={setLang} t={t} />

        <main className="flex-1">
          {installed ? (
            <Installed t={t} standalone={pwa.standalone} onShowSteps={() => setShowSteps(true)} />
          ) : (
            <>
              <Hero t={t} device={device} />
              <div className={cn('mt-6 grid gap-5', flow === 'desktop' && 'lg:grid-cols-[1fr_320px]')}>
                <section aria-labelledby="install-steps" className="min-w-0">
                  {flow === 'ios-safari' && <IosSafariFlow t={t} ipad={device.kind === 'ipad'} />}
                  {flow === 'ios-browser' && <IosBrowserFlow t={t} device={device} />}
                  {(flow === 'ios-in-app' || flow === 'android-in-app') && <InAppFlow t={t} device={device} />}
                  {flow === 'android' && <AndroidFlow t={t} device={device} />}
                  {flow === 'desktop' && <DesktopFlow t={t} device={device} />}
                </section>
                {flow === 'desktop' && <PhoneQr t={t} />}
              </div>
              <NextSteps t={t} />
            </>
          )}
          <Features t={t} />
        </main>

        <footer className="mt-10 space-y-3 text-center text-xs text-zinc-500">
          <ul className="flex flex-wrap justify-center gap-x-4 gap-y-1.5">
            {t.trust.map((item, i) => (
              <li key={item} className="inline-flex items-center gap-1.5">
                {[<UserRound key="u" className="size-3.5 text-emerald-600" aria-hidden />, <Lock key="l" className="size-3.5 text-emerald-600" aria-hidden />, <RefreshCw key="r" className="size-3.5 text-emerald-600" aria-hidden />][i]}
                {item}
              </li>
            ))}
          </ul>
          <p>{t.help}</p>
          <p className="text-zinc-400">© {new Date().getFullYear()} OkurmenKids</p>
        </footer>
      </div>
    </div>
  )
}

function Header({ lang, setLang, t }: { lang: InstallLang; setLang: (lang: InstallLang) => void; t: InstallText }) {
  return (
    <header className="flex items-center justify-between gap-3 py-2">
      <div className="flex min-w-0 items-center gap-2.5">
        <img src="/logo.png" alt="OkurmenKids" className="h-9 w-auto shrink-0" width={40} height={36} />
        <div className="min-w-0 leading-tight">
          <div className="truncate text-[15px] font-extrabold tracking-tight">
            Okurmen<span className="text-emerald-600">Kids</span> <span className="font-semibold text-zinc-500">LMS</span>
          </div>
          <div className="truncate text-[11px] text-zinc-500">{t.tagline}</div>
        </div>
      </div>
      <div role="group" aria-label={t.langLabel} className="flex shrink-0 rounded-full border border-zinc-200 bg-white p-0.5 text-xs font-semibold shadow-sm">
        {(['ru', 'kg'] as const).map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => setLang(id)}
            aria-pressed={lang === id}
            lang={id === 'kg' ? 'ky' : 'ru'}
            className={cn('min-w-10 rounded-full px-3 py-1.5 transition', RING, lang === id ? 'bg-emerald-600 text-white shadow' : 'text-zinc-600 hover:text-emerald-700')}
          >
            {id === 'kg' ? 'KG' : 'RU'}
          </button>
        ))}
      </div>
    </header>
  )
}

function Hero({ t, device }: { t: InstallText; device: DeviceInfo }) {
  return (
    <section className="mt-6 text-center sm:mt-10">
      <div className="relative mx-auto size-20 sm:size-24">
        <div aria-hidden className="absolute -inset-3 rounded-[2rem] bg-emerald-400/20 blur-xl" />
        <img src="/icons/icon-192.png" alt="" className="relative size-full rounded-[1.4rem] border border-zinc-200 bg-white shadow-[0_18px_40px_-18px_rgba(5,95,60,0.55)]" />
      </div>
      <h1 className="mx-auto mt-5 max-w-md text-[1.7rem] font-extrabold leading-tight tracking-tight sm:text-4xl">{t.title}</h1>
      <p className="mx-auto mt-2.5 max-w-lg text-[15px] leading-relaxed text-zinc-600">{t.subtitle}</p>
      <ul className="mt-4 flex flex-wrap justify-center gap-2">
        {t.perks.map((perk) => (
          <li key={perk} className="inline-flex items-center gap-1 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
            <Check className="size-3.5" aria-hidden />
            {perk}
          </li>
        ))}
      </ul>
      <p className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-zinc-100 px-3 py-1 text-xs text-zinc-600" data-testid="device-chip">
        <Smartphone className="size-3.5 text-zinc-500" aria-hidden />
        {t.device}: <b className="font-semibold text-zinc-800">{deviceLabel(device, { computer: t.computer, browser: t.browser })}</b>
      </p>
    </section>
  )
}

function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('rounded-3xl border border-zinc-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04),0_12px_32px_-18px_rgba(6,78,59,0.25)] sm:p-6', className)}>{children}</div>
}

function CardTitle({ children, id }: { children: ReactNode; id?: string }) {
  return <h2 id={id} className="text-lg font-bold tracking-tight">{children}</h2>
}

/** Numbered steps; with `active` the current one is highlighted and each is a button. */
function Steps({ items, active, onSelect, done = [], startAt = 1 }: {
  items: { title: string; text?: string }[]
  active?: number
  onSelect?: (index: number) => void
  done?: number[]
  startAt?: number
}) {
  return (
    <ol className="space-y-2">
      {items.map((item, index) => {
        const current = active === index
        const finished = done.includes(index)
        const body = (
          <>
            <span
              className={cn(
                'flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-bold transition',
                current ? 'bg-emerald-600 text-white shadow-[0_6px_16px_-6px_rgba(5,150,105,0.8)]' : finished ? 'bg-emerald-100 text-emerald-700' : 'bg-zinc-100 text-zinc-600',
              )}
            >
              {finished && !current ? <Check className="size-4" aria-hidden /> : index + startAt}
            </span>
            <span className="min-w-0 pt-1 text-left">
              <span className={cn('block text-[15px] font-semibold leading-snug', current ? 'text-zinc-900' : 'text-zinc-800')}>{item.title}</span>
              {item.text && <span className="mt-0.5 block text-sm leading-snug text-zinc-500">{item.text}</span>}
            </span>
          </>
        )
        return (
          <li key={index}>
            {onSelect ? (
              <button
                type="button"
                onClick={() => onSelect(index)}
                aria-current={current ? 'step' : undefined}
                className={cn('flex w-full items-start gap-3 rounded-2xl border p-3 transition', RING, current ? 'border-emerald-200 bg-emerald-50/70' : 'border-transparent hover:bg-zinc-50')}
              >
                {body}
              </button>
            ) : (
              <div className="flex items-start gap-3 rounded-2xl p-2">{body}</div>
            )}
          </li>
        )
      })}
    </ol>
  )
}

function IosSafariFlow({ t, ipad }: { t: InstallText; ipad: boolean }) {
  const reduce = useReducedMotion()
  const [step, setStep] = useState(0)
  const [auto, setAuto] = useState(!reduce)
  const steps = t.ios.steps.map((s) => ({ title: s.title, text: ipad && 'textIpad' in s && s.textIpad ? s.textIpad : s.text }))

  useEffect(() => {
    if (!auto) return
    const id = window.setTimeout(() => setStep((s) => (s + 1) % steps.length), step === steps.length - 1 ? 5200 : 3600)
    return () => window.clearTimeout(id)
  }, [auto, step, steps.length])

  const choose = (index: number) => {
    setAuto(false)
    setStep(index)
  }

  return (
    <Card>
      <CardTitle id="install-steps">{ipad ? t.ios.titleIpad : t.ios.title}</CardTitle>
      <div className="mt-5 grid items-center gap-6 sm:grid-cols-[auto_1fr]">
        <div className="flex flex-col items-center gap-3">
          <IosScene step={step} t={t} ipad={ipad} />
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => choose(Math.max(0, step - 1))} disabled={step === 0} aria-label={t.back}
              className={cn('flex size-9 items-center justify-center rounded-full border border-zinc-200 text-zinc-700 disabled:opacity-40', RING)}>
              <ChevronLeft className="size-4" aria-hidden />
            </button>
            <span className="min-w-16 text-center text-xs font-semibold text-zinc-500" aria-live="polite">
              {t.step} {step + 1} / {steps.length}
            </span>
            <button type="button" onClick={() => choose(Math.min(steps.length - 1, step + 1))} disabled={step === steps.length - 1} aria-label={t.forward}
              className={cn('flex size-9 items-center justify-center rounded-full border border-zinc-200 text-zinc-700 disabled:opacity-40', RING)}>
              <ChevronRight className="size-4" aria-hidden />
            </button>
          </div>
        </div>
        <Steps items={steps} active={step} onSelect={choose} done={[0]} />
      </div>
    </Card>
  )
}

function useCopy(t: InstallText): [string | null, () => void] {
  const [note, setNote] = useState<string | null>(null)
  const timer = useRef<number>(0)
  const copy = useCallback(() => {
    const url = `${window.location.origin}/install`
    const done = (ok: boolean) => {
      setNote(ok ? t.copied : t.copyFailed)
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setNote(null), 2500)
    }
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(url).then(() => done(true), () => done(false))
    } else {
      done(false)
    }
  }, [t.copied, t.copyFailed])
  useEffect(() => () => window.clearTimeout(timer.current), [])
  return [note, copy]
}

function CopyLink({ t, primary = false }: { t: InstallText; primary?: boolean }) {
  const [note, copy] = useCopy(t)
  const url = typeof window === 'undefined' ? '/install' : `${window.location.origin}/install`
  return (
    <div className="mt-4 space-y-2">
      <div className="flex items-center gap-2 rounded-2xl border border-zinc-200 bg-zinc-50 p-1.5 pl-3">
        <span className="min-w-0 flex-1 select-all truncate font-mono text-[13px] text-zinc-700">{url}</span>
        <button
          type="button"
          onClick={copy}
          className={cn(
            'inline-flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-semibold transition active:scale-[0.98]',
            RING,
            primary ? 'bg-emerald-600 text-white shadow hover:bg-emerald-700' : 'border border-zinc-200 bg-white text-zinc-800 hover:border-emerald-300',
          )}
        >
          <Copy className="size-4" aria-hidden />
          {t.copy}
        </button>
      </div>
      <p role="status" className="min-h-5 text-center text-sm font-medium text-emerald-700">{note}</p>
    </div>
  )
}

function IosBrowserFlow({ t, device }: { t: InstallText; device: DeviceInfo }) {
  const name = device.browser === 'chrome' ? 'Chrome' : device.browser === 'edge' ? 'Edge' : null
  // Since iOS 16.4 Chrome and Edge can add a web app from their own Share menu.
  const alt = name && (device.iosVersion === null || device.iosVersion >= 17) ? t.iosBrowser.alt(name) : null
  return (
    <Card>
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-sky-50 text-sky-600"><ExternalLink className="size-5" aria-hidden /></span>
        <div>
          <CardTitle id="install-steps">{t.iosBrowser.title}</CardTitle>
          <p className="mt-1 text-sm text-zinc-600">{t.iosBrowser.text}</p>
        </div>
      </div>
      <div className="mt-4">
        <Steps items={t.iosBrowser.steps.map((title) => ({ title }))} />
      </div>
      <CopyLink t={t} primary />
      {alt && <p className="rounded-2xl bg-zinc-50 p-3 text-sm text-zinc-600">{alt}</p>}
    </Card>
  )
}

function InAppFlow({ t, device }: { t: InstallText; device: DeviceInfo }) {
  const ios = device.os === 'ios'
  return (
    <Card>
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-amber-50 text-amber-600"><ExternalLink className="size-5" aria-hidden /></span>
        <div>
          <CardTitle id="install-steps">{t.inApp.title(device.inAppName)}</CardTitle>
          <p className="mt-1 text-sm text-zinc-600">{t.inApp.text}</p>
        </div>
      </div>
      <div className="mt-4">
        <Steps items={(ios ? t.inApp.iosSteps : t.inApp.androidSteps).map((title) => ({ title }))} />
      </div>
      <p className="mt-3 text-sm text-zinc-500">{t.inApp.orCopy}</p>
      <CopyLink t={t} primary />
    </Card>
  )
}

type PromptPhase = 'waiting' | 'ready' | 'none' | 'prompting' | 'dismissed'

/** The Chromium install button: the real `beforeinstallprompt` dialog, or nothing. */
function usePromptPhase(): [PromptPhase, () => Promise<void>] {
  const pwa = usePwaState()
  const [graceOver, setGraceOver] = useState(false)
  const [local, setLocal] = useState<'prompting' | 'dismissed' | null>(null)
  useEffect(() => {
    const id = window.setTimeout(() => setGraceOver(true), PROMPT_GRACE_MS)
    return () => window.clearTimeout(id)
  }, [])
  const install = useCallback(async () => {
    setLocal('prompting')
    const outcome = await promptInstall()
    setLocal(outcome === 'accepted' ? null : 'dismissed')
  }, [])
  // A fresh prompt after a dismissal is offered again.
  useEffect(() => {
    if (pwa.promptEvent) setLocal((l) => (l === 'dismissed' ? null : l))
  }, [pwa.promptEvent])
  const phase: PromptPhase = local === 'prompting' ? 'prompting' : pwa.promptEvent ? 'ready' : local === 'dismissed' ? 'dismissed' : graceOver ? 'none' : 'waiting'
  return [phase, install]
}

function InstallButton({ phase, onClick, label, t }: { phase: PromptPhase; onClick: () => void; label: string; t: InstallText }) {
  if (phase === 'none' || phase === 'dismissed') return null
  const busy = phase !== 'ready'
  return (
    <div className="mt-5">
      <button
        type="button"
        onClick={onClick}
        disabled={busy}
        className={cn(
          'flex w-full items-center justify-center gap-2.5 rounded-2xl bg-gradient-to-b from-emerald-500 to-emerald-600 px-6 py-4 text-[17px] font-bold text-white shadow-[0_14px_30px_-12px_rgba(5,150,105,0.85)] transition hover:from-emerald-600 hover:to-emerald-700 active:scale-[0.99] disabled:cursor-wait disabled:opacity-70',
          RING,
        )}
      >
        {busy ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <Download className="size-5" aria-hidden />}
        {phase === 'prompting' ? t.android.installing : phase === 'waiting' ? t.android.waiting : label}
      </button>
      {phase === 'ready' && <p className="mt-2 text-center text-sm text-zinc-500">{t.android.oneTap}</p>}
    </div>
  )
}

function AndroidFlow({ t, device }: { t: InstallText; device: DeviceInfo }) {
  const [phase, install] = usePromptPhase()
  const key = device.browser === 'samsung' || device.browser === 'firefox' || device.browser === 'edge' || device.browser === 'chrome' ? device.browser : 'other'
  const manualFirst = phase === 'none' || phase === 'dismissed'
  const bottomMenu = device.browser === 'samsung' || device.browser === 'edge'
  return (
    <Card>
      <CardTitle id="install-steps">{t.android.title}</CardTitle>
      <InstallButton phase={phase} onClick={() => void install()} label={t.android.install} t={t} />
      {phase === 'dismissed' && <p role="status" className="mt-3 rounded-2xl bg-amber-50 p-3 text-sm text-amber-900">{t.android.dismissed}</p>}
      <div className={cn('grid items-center gap-6 sm:grid-cols-[auto_1fr]', manualFirst ? 'mt-5' : 'mt-6 border-t border-zinc-100 pt-5')}>
        <AndroidScene t={t} menu={bottomMenu ? 'bottom-menu' : 'top-menu'} />
        <div>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-500">{manualFirst ? t.android.manualTitle : t.android.manualTitleAlt}</h3>
          <Steps items={t.android.steps[key].map((title) => ({ title }))} />
          {device.browser === 'samsung' && <p className="mt-2 text-sm text-zinc-500">{t.android.samsungIcon}</p>}
          {key === 'other' && <p className="mt-2 text-sm text-zinc-500">{t.android.otherHint}</p>}
        </div>
      </div>
    </Card>
  )
}

function DesktopFlow({ t, device }: { t: InstallText; device: DeviceInfo }) {
  const [phase, install] = usePromptPhase()
  const canInstall = desktopCanInstall(device)
  const steps = device.browser === 'safari' ? t.desktop.safariSteps : device.browser === 'edge' ? t.desktop.edgeSteps : t.desktop.chromeSteps
  return (
    <Card className="h-full">
      <CardTitle id="install-steps">{t.desktop.title}</CardTitle>
      {canInstall ? (
        <>
          {device.browser !== 'safari' && <InstallButton phase={phase} onClick={() => void install()} label={t.desktop.install} t={t} />}
          {phase === 'dismissed' && <p role="status" className="mt-3 rounded-2xl bg-amber-50 p-3 text-sm text-amber-900">{t.android.dismissed}</p>}
          <div className="mt-5">
            <Steps items={steps.map((title) => ({ title }))} />
          </div>
        </>
      ) : (
        <p className="mt-3 rounded-2xl bg-zinc-50 p-4 text-sm leading-relaxed text-zinc-700">{t.desktop.unsupported}</p>
      )}
    </Card>
  )
}

function PhoneQr({ t }: { t: InstallText }) {
  const url = `${window.location.origin}/install`
  return (
    <Card className="flex flex-col items-center text-center">
      <CardTitle>{t.desktop.phoneTitle}</CardTitle>
      <p className="mt-1 text-sm text-zinc-600">{t.desktop.phoneText}</p>
      <div className="mt-4 rounded-2xl border border-zinc-200 bg-white p-2">
        <QrCode value={url} withLogo label={t.qr.poster.scan} className="size-52" />
      </div>
      <p className="mt-3 break-all font-mono text-xs text-zinc-500">{url}</p>
    </Card>
  )
}

function Installed({ t, standalone, onShowSteps }: { t: InstallText; standalone: boolean; onShowSteps: () => void }) {
  const { status, user } = useAuth()
  const signedIn = status === 'authenticated' && user
  const target = signedIn ? homeFor(user.role, '/app/dashboard') : '/login'
  return (
    <section className="mx-auto mt-10 max-w-md text-center" aria-live="polite">
      <SuccessBadge />
      <h1 className="mt-6 text-3xl font-extrabold tracking-tight">{t.success.title}</h1>
      <p className="mt-2.5 text-[15px] leading-relaxed text-zinc-600">{standalone ? t.success.standalone : t.success.installedTab}</p>
      {standalone ? (
        <Link
          to={target}
          className={cn('mt-7 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-b from-emerald-500 to-emerald-600 px-6 py-4 text-[17px] font-bold text-white shadow-[0_14px_30px_-12px_rgba(5,150,105,0.85)] transition hover:to-emerald-700', RING)}
        >
          {signedIn ? t.success.open : t.success.login}
          <ChevronRight className="size-5" aria-hidden />
        </Link>
      ) : (
        <button type="button" onClick={onShowSteps} className={cn('mt-6 text-sm font-semibold text-emerald-700 underline-offset-4 hover:underline', RING)}>
          {t.replay}
        </button>
      )}
    </section>
  )
}

function NextSteps({ t }: { t: InstallText }) {
  return (
    <section className="mt-5">
      <Card className="bg-gradient-to-br from-emerald-50/80 to-white">
        <CardTitle>{t.next.title}</CardTitle>
        <div className="mt-3">
          <Steps items={t.next.steps.map((title) => ({ title }))} />
        </div>
      </Card>
    </section>
  )
}

const FEATURE_ICONS = [CalendarDays, BookOpenCheck, ClipboardCheck, Wallet, ChartColumn]

function Features({ t }: { t: InstallText }) {
  const reduce = useReducedMotion()
  return (
    <section className="mt-8">
      <h2 className="text-center text-sm font-semibold uppercase tracking-wider text-zinc-500">{t.features.title}</h2>
      <ul className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-5">
        {t.features.items.map((item, i) => {
          const Icon = FEATURE_ICONS[i]
          return (
            <motion.li
              key={item}
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 + i * 0.05 }}
              className={cn('flex items-center gap-2.5 rounded-2xl border border-zinc-100 bg-zinc-50/60 p-3 text-sm font-medium text-zinc-800 sm:flex-col sm:text-center', i === 4 && 'col-span-2 sm:col-span-1')}
            >
              <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-white text-emerald-600 shadow-sm ring-1 ring-zinc-100"><Icon className="size-[18px]" aria-hidden /></span>
              {item}
            </motion.li>
          )
        })}
      </ul>
    </section>
  )
}

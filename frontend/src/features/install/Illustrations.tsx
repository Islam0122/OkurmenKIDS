import { useEffect, useState, type ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { Bookmark, Check, ChevronLeft, Copy, Download, Menu, MoreHorizontal, MoreVertical, PlusSquare, Share } from 'lucide-react'

import { cn } from '@/utils/cn'

import type { InstallText } from './i18n'

/**
 * Drawn (not screenshotted) phone screens for the install steps: the button to
 * press pulses, sheets slide in, the app icon pops onto the Home Screen.
 * Decorative — every step is also written out in text next to it — so the
 * whole figure is aria-hidden. Motion stops under prefers-reduced-motion.
 */

const ICON = '/icons/icon-192.png'

/** The tap marker: a green ring that pulses over the button to press. */
function Tap({ className, label = false }: { className?: string; label?: boolean }) {
  const reduce = useReducedMotion()
  return (
    <span className={cn('pointer-events-none absolute flex items-center justify-center', className)}>
      <motion.span
        className={cn('absolute rounded-full border-2 border-emerald-500/80', label ? 'inset-0' : 'size-9 bg-emerald-400/20')}
        initial={reduce ? false : { scale: 0.5, opacity: 0 }}
        animate={reduce ? { scale: 1, opacity: 1 } : { scale: [0.5, 1.15, 1.35], opacity: [0, 0.9, 0] }}
        transition={reduce ? undefined : { duration: 1.4, repeat: Infinity, ease: 'easeOut' }}
      />
      {/* On a text button only the ring shows, so the label stays readable. */}
      {!label && <span className="size-3 rounded-full bg-emerald-500 shadow-[0_0_0_3px_rgba(255,255,255,0.9)]" />}
    </span>
  )
}

/** Cycles 0…count-1 every `ms` (frozen on the last phase with reduced motion). */
function usePhase(count: number, ms: number): number {
  const reduce = useReducedMotion()
  const [phase, setPhase] = useState(reduce ? count - 1 : 0)
  useEffect(() => {
    if (reduce) {
      setPhase(count - 1)
      return
    }
    setPhase(0)
    const id = window.setInterval(() => setPhase((p) => (p + 1) % count), ms)
    return () => window.clearInterval(id)
  }, [count, ms, reduce])
  return phase
}

export function PhoneFrame({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div aria-hidden className={cn('relative mx-auto w-[184px] shrink-0 sm:w-[200px]', className)}>
      <div className="relative aspect-[9/19] rounded-[2.4rem] border-[7px] border-zinc-900 bg-zinc-900 shadow-[0_24px_60px_-20px_rgba(15,80,45,0.45)]">
        <div className="relative h-full overflow-hidden rounded-[1.9rem] bg-white">
          <div className="absolute left-1/2 top-1.5 z-30 h-[18px] w-[64px] -translate-x-1/2 rounded-full bg-zinc-900" />
          {children}
        </div>
      </div>
    </div>
  )
}

/** A miniature of the /install page itself, as the phone shows it. */
function MiniPage({ dim = false }: { dim?: boolean }) {
  return (
    <div className={cn('absolute inset-0 px-3 pt-9 transition-opacity', dim && 'opacity-40')}>
      <div className="flex items-center gap-1.5">
        <img src={ICON} alt="" className="size-5 rounded-md border border-zinc-200" />
        <span className="h-1.5 w-14 rounded-full bg-zinc-800" />
      </div>
      <div className="mt-4 h-2.5 w-28 rounded-full bg-zinc-900" />
      <div className="mt-1.5 h-2.5 w-20 rounded-full bg-zinc-900" />
      <div className="mt-3 space-y-1">
        <div className="h-1.5 w-full rounded-full bg-zinc-200" />
        <div className="h-1.5 w-5/6 rounded-full bg-zinc-200" />
      </div>
      <div className="mt-4 h-16 rounded-xl border border-emerald-100 bg-emerald-50" />
      <div className="mt-2 h-10 rounded-xl border border-zinc-100 bg-zinc-50" />
    </div>
  )
}

function SafariBar({ tapShare = false, ipad = false }: { tapShare?: boolean; ipad?: boolean }) {
  if (ipad) {
    return (
      <div className="absolute inset-x-0 top-0 z-20 flex items-center gap-1.5 border-b border-zinc-200 bg-zinc-50/95 px-2 pb-1.5 pt-7">
        <div className="flex h-5 flex-1 items-center justify-center rounded-md bg-zinc-200/80 text-[7px] text-zinc-500">okurmenkids · install</div>
        <span className="relative flex size-5 items-center justify-center text-sky-600">
          <Share className="size-3.5" />
          {tapShare && <Tap className="inset-0" />}
        </span>
      </div>
    )
  }
  return (
    <div className="absolute inset-x-0 bottom-0 z-20 border-t border-zinc-200 bg-zinc-50/95 px-2.5 pb-3 pt-1.5">
      <div className="flex h-6 items-center justify-center rounded-lg bg-zinc-200/80 text-[7px] text-zinc-500">okurmenkids · install</div>
      <div className="mt-1.5 flex items-center justify-between px-1 text-sky-600">
        <ChevronLeft className="size-3.5" />
        <span className="relative flex size-5 items-center justify-center">
          <Share className="size-3.5" />
          {tapShare && <Tap className="inset-0" />}
        </span>
        <Bookmark className="size-3.5" />
        <MoreHorizontal className="size-3.5" />
      </div>
    </div>
  )
}

function ShareSheet({ t }: { t: InstallText }) {
  const reduce = useReducedMotion()
  return (
    <motion.div
      className="absolute inset-x-0 bottom-0 z-20 rounded-t-2xl border-t border-zinc-200 bg-zinc-100 px-2.5 pb-4 pt-2 shadow-2xl"
      initial={reduce ? false : { y: '100%' }}
      animate={{ y: 0 }}
      transition={{ type: 'spring', stiffness: 260, damping: 28 }}
    >
      <div className="mx-auto mb-2 h-1 w-8 rounded-full bg-zinc-300" />
      <div className="mb-2 flex items-center gap-1.5 rounded-lg bg-white p-1.5">
        <img src={ICON} alt="" className="size-6 rounded-md border border-zinc-200" />
        <div className="space-y-1">
          <div className="h-1.5 w-16 rounded-full bg-zinc-800" />
          <div className="h-1 w-10 rounded-full bg-zinc-300" />
        </div>
      </div>
      <div className="divide-y divide-zinc-100 overflow-hidden rounded-lg bg-white text-[8px] text-zinc-800">
        <div className="flex items-center justify-between px-2 py-1.5">{t.ios.copyItem}<Copy className="size-2.5 text-zinc-500" /></div>
        <div className="flex items-center justify-between px-2 py-1.5">{t.ios.bookmark}<Bookmark className="size-2.5 text-zinc-500" /></div>
        <div className="relative flex items-center justify-between bg-emerald-50 px-2 py-1.5 font-semibold text-emerald-900">
          {t.ios.addHome}
          <span className="relative flex size-4 items-center justify-center">
            <PlusSquare className="size-2.5" />
            <Tap className="inset-0" />
          </span>
        </div>
      </div>
    </motion.div>
  )
}

function AddDialog({ t }: { t: InstallText }) {
  return (
    <div className="absolute inset-0 z-20 bg-zinc-100 pt-8">
      <div className="flex items-center justify-between px-3 text-[8px]">
        <span className="text-sky-600">{t.ios.cancel}</span>
        <span className="relative font-bold text-sky-600">
          {t.ios.add}
          <Tap label className="-inset-x-2 -inset-y-1.5" />
        </span>
      </div>
      <div className="mx-2.5 mt-3 flex items-center gap-2 rounded-lg bg-white p-2">
        <img src={ICON} alt="" className="size-9 rounded-xl border border-zinc-200" />
        <div className="min-w-0">
          <div className="text-[9px] font-semibold text-zinc-900">OkurmenKids</div>
          <div className="truncate text-[7px] text-zinc-400">okurmenkids · install</div>
        </div>
      </div>
      <div className="mx-2.5 mt-2 flex items-center justify-between rounded-lg bg-white px-2 py-1.5 text-[7.5px] text-zinc-800">
        {t.ios.webApp}
        <span className="flex h-3 w-5 items-center justify-end rounded-full bg-emerald-500 px-0.5"><span className="size-2 rounded-full bg-white" /></span>
      </div>
    </div>
  )
}

/** Home Screen with the OkurmenKids icon popping in among the others. */
export function HomeScreen({ android = false }: { android?: boolean }) {
  const reduce = useReducedMotion()
  const tiles = ['bg-sky-400', 'bg-amber-400', 'bg-rose-400', 'bg-violet-400', 'bg-teal-400', 'bg-orange-400', 'bg-lime-500']
  return (
    <div className={cn('absolute inset-0 z-20 px-3 pt-10', android ? 'bg-gradient-to-b from-emerald-800 to-teal-900' : 'bg-gradient-to-b from-sky-300 via-emerald-200 to-emerald-400')}>
      <div className="grid grid-cols-4 gap-x-2 gap-y-3">
        {tiles.map((tile, i) => (
          <div key={i} className="flex flex-col items-center gap-0.5">
            <span className={cn('size-8 rounded-[0.6rem] opacity-90', tile)} />
            <span className="h-1 w-6 rounded-full bg-white/60" />
          </div>
        ))}
        <div className="flex flex-col items-center gap-0.5">
          <motion.img
            src={ICON}
            alt=""
            className="size-8 rounded-[0.6rem] bg-white shadow-lg ring-2 ring-white"
            initial={reduce ? false : { scale: 0, rotate: -12 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ type: 'spring', stiffness: 320, damping: 14, delay: 0.25 }}
          />
          <span className="text-[6px] font-semibold text-white drop-shadow">OkurmenKids</span>
        </div>
      </div>
    </div>
  )
}

/** iPhone / iPad Safari, one scene per step (0 Safari, 1 Share, 2 Home Screen, 3 Add → icon). */
export function IosScene({ step, t, ipad = false }: { step: number; t: InstallText; ipad?: boolean }) {
  const phase = usePhase(2, 1900)
  return (
    <PhoneFrame>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={step === 3 ? `3-${phase}` : step} className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
          {step === 0 && (
            <>
              <MiniPage />
              <SafariBar ipad={ipad} />
              <div className="absolute left-1/2 top-1/2 z-20 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1 rounded-2xl bg-white/95 px-3 py-2 shadow-lg ring-1 ring-zinc-200">
                <SafariGlyph />
                <span className="flex items-center gap-0.5 text-[8px] font-semibold text-emerald-700"><Check className="size-2.5" />Safari</span>
              </div>
            </>
          )}
          {step === 1 && (
            <>
              <MiniPage />
              <SafariBar tapShare ipad={ipad} />
            </>
          )}
          {step === 2 && (
            <>
              <MiniPage dim />
              <ShareSheet t={t} />
            </>
          )}
          {step === 3 && (phase === 0 ? <AddDialog t={t} /> : <HomeScreen />)}
        </motion.div>
      </AnimatePresence>
    </PhoneFrame>
  )
}

function SafariGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="size-7" aria-hidden>
      <circle cx="12" cy="12" r="11" fill="#e0f2fe" stroke="#0284c7" strokeWidth="1.5" />
      <path d="M15.8 8.2 13 13l-4.8 2.8L11 11z" fill="#ef4444" />
      <path d="M11 11 8.2 15.8 13 13z" fill="#0284c7" />
    </svg>
  )
}

export type AndroidBrowserStyle = 'top-menu' | 'bottom-menu'

/** Android: menu → «Установить приложение» → confirm → icon on the Home Screen. */
export function AndroidScene({ t, menu = 'top-menu' }: { t: InstallText; menu?: AndroidBrowserStyle }) {
  const phase = usePhase(4, 1700)
  const bottom = menu === 'bottom-menu'
  const MenuIcon = bottom ? Menu : MoreVertical
  return (
    <PhoneFrame>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={phase} className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
          {phase === 3 ? (
            <HomeScreen android />
          ) : (
            <>
              <MiniPage dim={phase > 0} />
              <div className={cn('absolute inset-x-0 z-20 flex items-center gap-1.5 bg-white px-2 py-1.5 shadow-sm', bottom ? 'bottom-0 pb-3' : 'top-0 pt-7')}>
                <div className="flex h-5 flex-1 items-center rounded-full bg-zinc-100 px-2 text-[7px] text-zinc-500">okurmenkids/install</div>
                <span className="relative flex size-5 items-center justify-center text-zinc-700">
                  <MenuIcon className="size-3.5" />
                  {phase === 0 && <Tap className="inset-0" />}
                </span>
              </div>
              {phase === 1 && (
                <motion.div
                  className={cn('absolute z-30 w-[70%] overflow-hidden rounded-lg bg-white text-[7.5px] text-zinc-800 shadow-xl ring-1 ring-zinc-200', bottom ? 'bottom-12 left-3 right-3 w-auto' : 'right-1.5 top-14')}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                >
                  {t.android.menuItems.map((item) => <div key={item} className="px-2 py-1.5">{item}</div>)}
                  <div className="relative flex items-center gap-1 bg-emerald-50 px-2 py-1.5 font-semibold text-emerald-900">
                    <Download className="size-2.5" />
                    {t.android.menuInstall}
                    <Tap className="right-1 top-1/2 -translate-y-1/2" />
                  </div>
                </motion.div>
              )}
              {phase === 2 && <AndroidDialog t={t} />}
            </>
          )}
        </motion.div>
      </AnimatePresence>
    </PhoneFrame>
  )
}

function AndroidDialog({ t }: { t: InstallText }) {
  return (
    <motion.div
      className="absolute inset-x-2.5 top-1/3 z-30 rounded-2xl bg-white p-2.5 shadow-2xl ring-1 ring-zinc-200"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="text-[8.5px] font-semibold text-zinc-900">{t.android.dialogTitle}</div>
      <div className="mt-2 flex items-center gap-1.5">
        <img src={ICON} alt="" className="size-7 rounded-lg border border-zinc-200" />
        <div>
          <div className="text-[8px] font-semibold text-zinc-900">OkurmenKids</div>
          <div className="text-[6.5px] text-zinc-400">okurmenkids</div>
        </div>
      </div>
      <div className="mt-2.5 flex justify-end gap-2 text-[7.5px] font-semibold">
        <span className="text-zinc-500">{t.ios.cancel}</span>
        <span className="relative text-emerald-700">
          {t.android.dialogInstall}
          <Tap label className="-inset-x-2 -inset-y-1.5" />
        </span>
      </div>
    </motion.div>
  )
}

/** Animated check for the «installed» screen. */
export function SuccessBadge() {
  const reduce = useReducedMotion()
  return (
    <div aria-hidden className="relative mx-auto flex size-24 items-center justify-center">
      {!reduce && (
        <motion.span
          className="absolute inset-0 rounded-full bg-emerald-400/25"
          initial={{ scale: 0.6, opacity: 0.9 }}
          animate={{ scale: 1.5, opacity: 0 }}
          transition={{ duration: 1.6, repeat: Infinity, ease: 'easeOut' }}
        />
      )}
      <motion.span
        className="relative flex size-20 items-center justify-center rounded-full bg-gradient-to-br from-emerald-500 to-green-600 text-white shadow-[0_16px_40px_-12px_rgba(22,163,74,0.7)]"
        initial={reduce ? false : { scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ type: 'spring', stiffness: 260, damping: 16 }}
      >
        <svg viewBox="0 0 24 24" className="size-10" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
          <motion.path d="M5 12.5l4.2 4.2L19 7" initial={reduce ? false : { pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.5, delay: 0.25 }} />
        </svg>
      </motion.span>
    </div>
  )
}

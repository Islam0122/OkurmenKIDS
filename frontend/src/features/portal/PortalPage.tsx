import { useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'

import { AppCard } from './AppCard'
import { PORTAL_APPS, isVisible, resolveCard, type CardState } from './config'
import { PortalShell } from './PortalShell'

const gridVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.045, delayChildren: 0.08 } },
}

/** OKURMEN DIGITAL — one screen, every academy application. */
export function PortalPage() {
  const { user, status } = useAuth()
  const navigate = useNavigate()
  const signedIn = status === 'authenticated' ? user : null

  const cards = useMemo(
    () =>
      PORTAL_APPS.filter((app) => isVisible(app, signedIn)).map((app) => ({ app, state: resolveCard(app, signedIn) })),
    [signedIn],
  )

  // 1–7 opens the matching app, like a launcher dock.
  useEffect(() => {
    function open(state: CardState) {
      if (state.kind === 'unavailable') return
      if (state.kind === 'login') navigate('/login', { state: { from: { pathname: state.href, search: '' } } })
      else if (state.external) window.open(state.href, '_blank', 'noopener,noreferrer')
      else navigate(state.href)
    }
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey || event.repeat) return
      const target = event.target as HTMLElement | null
      if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return
      const index = Number(event.key) - 1
      if (Number.isInteger(index) && index >= 0 && index < cards.length) open(cards[index].state)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cards, navigate])

  const firstName = signedIn?.first_name || signedIn?.username

  return (
    <PortalShell>
      <main className="mx-auto flex w-full max-w-[1100px] flex-1 flex-col justify-center px-4 pb-6 pt-1 sm:px-6 lg:pb-8">
        <motion.section
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: 'easeOut' }}
          className="mb-6 text-center sm:mb-7"
        >
          <p className="inline-flex items-center gap-2 rounded-full border border-pd-line bg-pd-panel/70 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-pd-muted backdrop-blur">
            <span className="size-1.5 rounded-full bg-pd-green" aria-hidden />
            {firstName ? `Hello, ${firstName}` : 'Everything you need to learn, teach and grow.'}
          </p>
          <h1 className="mt-3.5 text-balance text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-[2.75rem]">
            Welcome to Okurmen <span className="text-pd-green">Digital</span>
          </h1>
          <p className="mx-auto mt-2.5 max-w-lg text-pretty text-sm text-pd-muted sm:text-base">
            Your central platform for education, training, performance and academy resources.
          </p>
        </motion.section>

        <motion.ul
          variants={gridVariants}
          initial="hidden"
          animate="show"
          className="grid grid-flow-row-dense grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 lg:grid-cols-4"
          aria-label="Academy applications"
        >
          {cards.map(({ app, state }, index) => (
            <AppCard key={app.id} app={app} state={state} shortcut={index + 1} />
          ))}
        </motion.ul>

        <p className="mt-5 hidden text-center text-xs text-pd-faint lg:block">
          Press <kbd className="rounded border border-pd-line px-1 font-mono">1</kbd>–
          <kbd className="rounded border border-pd-line px-1 font-mono">{cards.length}</kbd> to open an application
        </p>
      </main>
    </PortalShell>
  )
}

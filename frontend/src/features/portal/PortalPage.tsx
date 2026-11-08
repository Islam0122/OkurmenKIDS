import { useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'

import { AppCard } from './AppCard'
import { PORTAL_APPS, PORTAL_SERVICES, isVisible, resolveCard, resolveService, type CardState } from './config'
import { useI18n } from './i18n'
import { PortalShell } from './PortalShell'
import { ServiceCard } from './ServiceCard'

const gridVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.045, delayChildren: 0.08 } },
}

/** OKURMEN DIGITAL — one screen, every academy application. */
export function PortalPage() {
  return (
    <PortalShell>
      <Launcher />
    </PortalShell>
  )
}

function Launcher() {
  const { t } = useI18n()
  const { user, status } = useAuth()
  const navigate = useNavigate()
  const signedIn = status === 'authenticated' ? user : null

  const cards = useMemo(
    () =>
      PORTAL_APPS.filter((app) => isVisible(app, signedIn)).map((app) => ({ app, state: resolveCard(app, signedIn) })),
    [signedIn],
  )

  const services = useMemo(
    () =>
      PORTAL_SERVICES.filter((service) => isVisible(service, signedIn)).map((service) => ({ service, state: resolveService(service, signedIn) })),
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
      // Not while About/Help/Privacy is open.
      if (document.querySelector('[role="dialog"][aria-modal="true"]')) return
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
    <main className="mx-auto flex w-full max-w-[1100px] flex-1 flex-col justify-center px-4 py-6 sm:px-6 lg:py-5 short:py-3">
        <motion.section
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: 'easeOut' }}
          className="mb-5 text-center sm:mb-7 short:mb-4"
        >
          <p className="hidden max-w-full items-center gap-2 rounded-full sm:inline-flex short:hidden border border-pd-line bg-pd-panel px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-pd-muted pd-shadow">
            <span className="relative flex size-1.5 shrink-0" aria-hidden>
              <span className="absolute inset-0 animate-ping rounded-full bg-pd-green/60" />
              <span className="relative size-1.5 rounded-full bg-pd-green" />
            </span>
            <span className="truncate">{firstName ? t.hero.hello(firstName) : t.hero.tagline}</span>
          </p>
          <h1 className="mt-3.5 text-balance short:mt-0 short:lg:text-[2.25rem] text-[1.75rem] font-extrabold leading-[1.1] tracking-[-0.03em] sm:text-4xl lg:text-[2.6rem]">
            {t.hero.title.before}
            <span className="text-pd-green">{t.hero.title.accent}</span>
            {t.hero.title.after}
          </h1>
          <p className="mx-auto mt-2.5 max-w-lg text-pretty tiny:hidden text-sm text-pd-muted sm:text-[15px]">{t.hero.description}</p>
        </motion.section>

        <motion.ul
          variants={gridVariants}
          initial="hidden"
          animate="show"
          className="grid grid-flow-row-dense grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 lg:grid-cols-4"
          aria-label={t.hero.appsLabel}
        >
          {cards.map(({ app, state }, index) => (
            <AppCard key={app.id} app={app} state={state} shortcut={index + 1} />
          ))}
        </motion.ul>

        {services.length > 0 ? (
          <section aria-labelledby="more-from-okurmen" className="mt-6 sm:mt-7 short:mt-4">
            <div className="mb-3 flex items-center gap-3">
              <h2 id="more-from-okurmen" className="shrink-0 text-[11px] font-semibold uppercase tracking-[0.18em] text-pd-faint">
                {t.servicesTitle}
              </h2>
              <span aria-hidden className="h-px flex-1 bg-gradient-to-r from-pd-line to-transparent" />
            </div>
            <motion.ul
              variants={gridVariants}
              initial="hidden"
              animate="show"
              className="grid gap-2.5 sm:grid-cols-2 sm:gap-3 lg:grid-cols-[repeat(auto-fit,minmax(0,1fr))]"
            >
              {services.map(({ service, state }) => (
                <ServiceCard key={service.id} service={service} state={state} />
              ))}
            </motion.ul>
          </section>
        ) : null}
    </main>
  )
}

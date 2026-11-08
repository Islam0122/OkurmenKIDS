import { motion } from 'framer-motion'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { cardVariants } from './AppCard'
import { PORTAL_APPS, PORTAL_PATH, PROGRAMS, resolveCard } from './config'
import { useI18n } from './i18n'
import { PortalShell } from './PortalShell'

/** «Our Programs» — the academy's learning directions, on the same white screen. */
export function ProgramsPage() {
  return (
    <PortalShell page="programs">
      <Programs />
    </PortalShell>
  )
}

function Programs() {
  const { t } = useI18n()
  const p = t.programsPage
  const training = PORTAL_APPS.find((app) => app.id === 'training')
  const trainingState = training ? resolveCard(training, null) : null

  return (
    <main className="mx-auto flex w-full max-w-[1100px] flex-1 flex-col justify-center px-4 py-6 sm:px-6">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="mb-6 sm:mb-8">
        <Link
          to={PORTAL_PATH}
          className="inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-pd-muted transition hover:text-pd-green focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-pd-green"
        >
          <ArrowLeft className="size-4" aria-hidden /> {p.back}
        </Link>
        <h1 className="mt-4 text-3xl font-extrabold tracking-[-0.03em] sm:text-4xl">
          {p.title} <span className="text-pd-green">{p.titleAccent}</span>
        </h1>
        <p className="mt-2 max-w-xl text-sm text-pd-muted sm:text-base">{p.subtitle}</p>
      </motion.div>

      <motion.ul
        initial="hidden"
        animate="show"
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.06 } } }}
        className="grid gap-3 sm:grid-cols-2 sm:gap-4"
      >
        {PROGRAMS.map((program) => {
          const Icon = program.icon
          const text = t.programs[program.id]
          return (
            <motion.li
              key={program.id}
              variants={cardVariants}
              whileHover={{ y: -3 }}
              className="group relative overflow-hidden rounded-2xl border border-pd-line bg-pd-panel p-5 pd-shadow transition-[border-color,box-shadow] duration-300 hover:border-pd-green-line hover:pd-shadow-lg"
            >
              <div className="flex items-start gap-4">
                <span className="grid size-11 shrink-0 place-items-center rounded-xl border border-pd-green-line bg-pd-green-soft text-pd-green">
                  <Icon className="size-5" strokeWidth={1.75} aria-hidden />
                </span>
                <div className="min-w-0">
                  <h2 className="text-base font-bold tracking-tight">{text.name}</h2>
                  <p className="mt-1 text-sm leading-snug text-pd-muted">{text.summary}</p>
                  <ul className="mt-3 flex flex-wrap gap-1.5">
                    {text.topics.map((topic) => (
                      <li key={topic} className="rounded-md border border-pd-line bg-pd-subtle px-1.5 py-0.5 text-[11px] font-medium text-pd-muted">
                        {topic}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </motion.li>
          )
        })}
      </motion.ul>

      {trainingState?.kind === 'open' ? (
        <div className="mt-6 flex flex-col items-start justify-between gap-3 rounded-2xl border border-pd-green-line bg-pd-green-soft p-4 sm:flex-row sm:items-center">
          <p className="text-sm text-pd-muted">{p.cta}</p>
          <a
            href={trainingState.href}
            target={trainingState.external ? '_blank' : undefined}
            rel={trainingState.external ? 'noopener noreferrer' : undefined}
            className="inline-flex h-9 shrink-0 items-center gap-2 rounded-lg bg-pd-green px-3.5 text-sm font-semibold text-white pd-shadow transition hover:bg-pd-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pd-green"
          >
            {p.ctaButton} <ArrowRight className="size-4" aria-hidden />
          </a>
        </div>
      ) : null}
    </main>
  )
}

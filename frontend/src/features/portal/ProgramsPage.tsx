import { motion } from 'framer-motion'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { cardVariants } from './AppCard'
import { PORTAL_APPS, PORTAL_PATH, PROGRAMS, resolveCard } from './config'
import { PortalShell } from './PortalShell'

/** «Our Programs» — the academy's learning directions, on the same dark screen. */
export function ProgramsPage() {
  const training = PORTAL_APPS.find((app) => app.id === 'training')
  const trainingState = training ? resolveCard(training, null) : null

  return (
    <PortalShell>
      <main className="mx-auto flex w-full max-w-[1100px] flex-1 flex-col justify-center px-4 pb-8 pt-2 sm:px-6">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="mb-6 sm:mb-8">
          <Link
            to={PORTAL_PATH}
            className="inline-flex items-center gap-1.5 rounded-lg text-sm text-pd-muted transition hover:text-pd-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-pd-green"
          >
            <ArrowLeft className="size-4" aria-hidden /> All applications
          </Link>
          <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">
            Our <span className="text-pd-green">Programs</span>
          </h1>
          <p className="mt-2 max-w-xl text-sm text-pd-muted sm:text-base">Explore our educational programs and discover your learning path.</p>
        </motion.div>

        <motion.ul
          initial="hidden"
          animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.06 } } }}
          className="grid gap-3 sm:grid-cols-2 sm:gap-4"
        >
          {PROGRAMS.map((program) => {
            const Icon = program.icon
            return (
              <motion.li
                key={program.id}
                variants={cardVariants}
                whileHover={{ y: -3 }}
                className="group relative overflow-hidden rounded-2xl border border-pd-line bg-pd-panel/90 p-5 transition-colors duration-300 hover:border-pd-line-strong hover:bg-pd-panel-hover"
              >
                <div className="flex items-start gap-4">
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl border border-pd-line bg-pd-bg text-pd-ink transition-colors group-hover:border-pd-green/40 group-hover:text-pd-green">
                    <Icon className="size-5" strokeWidth={1.75} aria-hidden />
                  </span>
                  <div className="min-w-0">
                    <h2 className="text-base font-bold tracking-tight">{program.name}</h2>
                    <p className="mt-1 text-sm leading-snug text-pd-muted">{program.summary}</p>
                    <ul className="mt-3 flex flex-wrap gap-1.5">
                      {program.topics.map((topic) => (
                        <li key={topic} className="rounded-md border border-pd-line bg-pd-bg/60 px-1.5 py-0.5 text-[11px] text-pd-faint">
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
          <div className="mt-6 flex flex-col items-start justify-between gap-3 rounded-2xl border border-pd-line bg-pd-panel/60 p-4 sm:flex-row sm:items-center">
            <p className="text-sm text-pd-muted">Already studying? Practice and take tests in the training portal.</p>
            <a
              href={trainingState.href}
              target={trainingState.external ? '_blank' : undefined}
              rel={trainingState.external ? 'noopener noreferrer' : undefined}
              className="inline-flex h-9 shrink-0 items-center gap-2 rounded-lg bg-pd-green px-3.5 text-sm font-semibold text-pd-bg transition hover:brightness-110"
            >
              Training & Exams <ArrowRight className="size-4" aria-hidden />
            </a>
          </div>
        ) : null}
      </main>
    </PortalShell>
  )
}

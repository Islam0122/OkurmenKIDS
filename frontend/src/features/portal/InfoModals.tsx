import { CircleHelp, Code2, Info, KeyRound, LayoutGrid, LifeBuoy, LogIn, MousePointerClick, ShieldCheck, Target } from 'lucide-react'

import logo from '@/assets/logo-careers.png'

import { useI18n } from './i18n'
import { PortalModal } from './PortalModal'

export type InfoModalId = 'about' | 'help' | 'privacy'

const TECHNOLOGIES = ['Python', 'Django', 'React', 'TypeScript', 'PostgreSQL', 'Docker', 'REST API']
const DEVELOPER = 'Islam Duishobaev'

interface InfoModalsProps {
  open: InfoModalId | null
  onClose: () => void
}

/** The three header/footer dialogs. Only one is open at a time. */
export function InfoModals({ open, onClose }: InfoModalsProps) {
  return (
    <>
      <AboutModal open={open === 'about'} onClose={onClose} />
      <HelpModal open={open === 'help'} onClose={onClose} />
      <PrivacyModal open={open === 'privacy'} onClose={onClose} />
    </>
  )
}

function SectionTitle({ children }: { children: string }) {
  return <h3 className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-pd-faint">{children}</h3>
}

function AboutModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n()
  const a = t.about
  return (
    <PortalModal
      open={open}
      onClose={onClose}
      size="lg"
      title={a.title}
      subtitle={a.subtitle}
      icon={<img src={logo} alt="" className="size-8 object-contain" />}
      footer={
        <div className="space-y-0.5 text-center text-xs text-pd-faint">
          {a.footer.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      }
    >
      <div className="space-y-6">
        <div className="space-y-2 text-sm leading-relaxed text-pd-muted">
          {a.description.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>

        <section>
          <SectionTitle>{a.infoTitle}</SectionTitle>
          <dl className="grid gap-px overflow-hidden rounded-xl border border-pd-line bg-pd-line sm:grid-cols-2">
            {a.info.map((row) => (
              <div key={row.label} className="flex items-baseline justify-between gap-3 bg-pd-panel px-3.5 py-2.5 text-sm sm:odd:last:col-span-2">
                <dt className="text-pd-faint">{row.label}</dt>
                <dd className="text-right font-medium">{row.value}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section>
          <SectionTitle>{a.developerTitle}</SectionTitle>
          <div className="rounded-xl border border-pd-line p-4">
            <div className="flex items-center gap-3">
              <span className="grid size-11 shrink-0 place-items-center rounded-full bg-pd-ink text-sm font-bold text-white" aria-hidden>
                ID
              </span>
              <div>
                <p className="font-semibold">{DEVELOPER}</p>
                <p className="flex items-center gap-1.5 text-sm text-pd-muted">
                  <Code2 className="size-3.5 text-pd-green" aria-hidden />
                  {a.developerRole}
                </p>
              </div>
            </div>
            <ul className="mt-3.5 flex flex-wrap gap-1.5" aria-label={a.technologies}>
              {TECHNOLOGIES.map((tech) => (
                <li key={tech} className="rounded-full border border-pd-green-line bg-pd-green-soft px-2.5 py-0.5 text-xs font-medium text-pd-green-deep">
                  {tech}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="flex gap-3 rounded-xl border border-pd-green-line bg-pd-green-soft/60 p-4">
          <Target className="mt-0.5 size-5 shrink-0 text-pd-green" aria-hidden />
          <div>
            <h3 className="text-sm font-semibold">{a.missionTitle}</h3>
            <p className="mt-1 text-sm leading-relaxed text-pd-muted">{a.mission}</p>
          </div>
        </section>
      </div>
    </PortalModal>
  )
}

const HELP_ICONS = [MousePointerClick, LogIn, LayoutGrid, LifeBuoy]

function HelpModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n()
  return (
    <PortalModal
      open={open}
      onClose={onClose}
      title={t.help.title}
      subtitle={t.help.subtitle}
      icon={<CircleHelp className="size-5" aria-hidden />}
      footer={<p className="text-center text-xs text-pd-faint">{t.help.shortcut}</p>}
    >
      <ol className="space-y-2.5">
        {t.help.sections.map((section, index) => {
          const Icon = HELP_ICONS[index] ?? Info
          return (
            <li key={section.title} className="flex gap-3 rounded-xl border border-pd-line p-3.5">
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-pd-subtle text-pd-green ring-1 ring-pd-line">
                <Icon className="size-4" aria-hidden />
              </span>
              <div>
                <h3 className="text-sm font-semibold">{section.title}</h3>
                <p className="mt-0.5 text-sm leading-snug text-pd-muted">{section.text}</p>
              </div>
            </li>
          )
        })}
      </ol>
    </PortalModal>
  )
}

const PRIVACY_ICONS = [ShieldCheck, KeyRound, LifeBuoy]

function PrivacyModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n()
  return (
    <PortalModal open={open} onClose={onClose} title={t.privacy.title} icon={<ShieldCheck className="size-5" aria-hidden />}>
      <ul className="space-y-3">
        {t.privacy.sections.map((section, index) => {
          const Icon = PRIVACY_ICONS[index] ?? Info
          return (
            <li key={section.title} className="flex gap-3">
              <Icon className="mt-0.5 size-4 shrink-0 text-pd-green" aria-hidden />
              <div>
                <h3 className="text-sm font-semibold">{section.title}</h3>
                <p className="mt-0.5 text-sm leading-snug text-pd-muted">{section.text}</p>
              </div>
            </li>
          )
        })}
      </ul>
    </PortalModal>
  )
}

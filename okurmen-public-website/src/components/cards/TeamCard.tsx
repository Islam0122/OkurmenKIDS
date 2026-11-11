import { ArrowRight, Briefcase } from 'lucide-react'

import { SmartImage } from '@/components/shared/SmartImage'
import { useI18n } from '@/i18n'
import type { TeamMember } from '@/types/api'

export function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase()
}

/** Placeholder when the photo is not approved for the site: initials on a brand tint (never a fake face). */
export function TeamPhoto({ member, sizes, className }: { member: TeamMember; sizes?: string; className?: string }) {
  return (
    <SmartImage
      image={member.photo}
      alt={member.name}
      sizes={sizes ?? '(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw'}
      className={className}
      fallback={<span className="font-display text-6xl font-black text-brand-300">{initials(member.name)}</span>}
    />
  )
}

/**
 * A team member from GET /api/v1/public/site/team/ (approved public profiles only).
 * `onOpen` adds the «profile» button (Team page); without it the card is compact (homepage).
 */
export function TeamCard({ member, onOpen }: { member: TeamMember; onOpen?: () => void }) {
  const { t } = useI18n()
  const experience = member.experience_years ? t('team.years', { count: member.experience_years }) : null
  const tag = member.group ? t(`team.group.${member.group}`) : null
  const body = (
    <>
      <div className="relative aspect-[4/5] overflow-hidden bg-gradient-to-br from-brand-100 via-brand-50 to-gold-50">
        <TeamPhoto member={member} className="size-full object-top transition duration-700 ease-out group-hover:scale-[1.04]" />
        <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-brand-950/45 to-transparent opacity-0 transition duration-500 group-hover:opacity-100" />
        {experience ? (
          <span className="absolute top-3 left-3 inline-flex items-center gap-1.5 rounded-full bg-white/95 px-2.5 py-1 text-xs font-bold text-brand-800 shadow-soft backdrop-blur">
            <Briefcase className="size-3.5 text-gold-500" aria-hidden /> {experience}
          </span>
        ) : null}
      </div>
      <div className="flex flex-1 flex-col p-5 sm:p-6">
        {tag ? <span className="mb-2 self-start rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-bold tracking-wide text-brand-600 uppercase">{tag}</span> : null}
        <h3 className="text-lg leading-tight font-extrabold sm:text-xl">{member.name}</h3>
        <p className="mt-1 text-sm font-bold text-gold-600">{member.position}</p>
        {member.specialization ? <p className="mt-2 text-sm text-ink-soft">{member.specialization}</p> : null}
        {onOpen && member.bio ? <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-muted">{member.bio}</p> : null}
        {onOpen ? (
          <span className="mt-auto inline-flex items-center gap-1.5 pt-5 text-sm font-bold text-brand-700 transition group-hover:text-brand-900">
            {t('team.details')} <ArrowRight className="size-4 transition group-hover:translate-x-1" aria-hidden />
          </span>
        ) : null}
      </div>
    </>
  )
  const frame = 'card group flex h-full flex-col overflow-hidden text-left transition duration-300 hover:-translate-y-1 hover:border-brand-200 hover:shadow-lift'
  return onOpen ? (
    <button type="button" onClick={onOpen} className={frame} aria-haspopup="dialog">{body}</button>
  ) : (
    <article className={frame}>{body}</article>
  )
}

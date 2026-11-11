import { ArrowRight, UserRound } from 'lucide-react'
import { Link } from 'react-router-dom'

import { SmartImage } from '@/components/shared/SmartImage'
import { useI18n } from '@/i18n'
import type { TeamMember } from '@/types/api'
import { cn } from '@/utils/cn'

/** «Backend, Full-Stack, Python» → ['Backend', 'Full-Stack', 'Python'] */
export function specializationTags(value: string | null, limit = Infinity): string[] {
  if (!value) return []
  return value.split(/\s*[,;·|]\s*/).map((t) => t.trim()).filter(Boolean).slice(0, limit)
}

/** Approved photo, or a neutral silhouette placeholder (never a stand-in face). */
export function TeamPhoto({ member, sizes, className, priority }: { member: TeamMember; sizes?: string; className?: string; priority?: boolean }) {
  return (
    <SmartImage
      image={member.photo}
      alt={member.name}
      priority={priority}
      sizes={sizes ?? '(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw'}
      className={className}
      fallback={
        <span className="flex flex-col items-center gap-2 text-brand-200">
          <UserRound className="size-20" strokeWidth={1.25} aria-hidden />
        </span>
      }
    />
  )
}

/**
 * A team member from GET /api/v1/public/site/team/ — links to the profile
 * page /team/:slug. `lead` = the wider leadership card (photo beside text on desktop).
 */
export function TeamCard({ member, variant = 'default' }: { member: TeamMember; variant?: 'default' | 'lead' }) {
  const { t, path } = useI18n()
  const lead = variant === 'lead'
  const tags = specializationTags(member.specialization, lead ? 5 : 3)
  return (
    <Link
      to={path(`/team/${member.slug}`)}
      className={cn(
        'card group flex h-full w-full flex-col overflow-hidden bg-white transition duration-300 hover:-translate-y-1 hover:border-brand-200 hover:shadow-lift focus-visible:-translate-y-1',
        lead && 'sm:flex-row',
      )}
    >
      <div className={cn('relative aspect-[4/5] shrink-0 overflow-hidden bg-gradient-to-b from-surface-purple to-brand-50', lead && 'sm:w-[42%]')}>
        <TeamPhoto member={member} sizes={lead ? '(min-width: 640px) 260px, 100vw' : undefined}
          className="size-full object-top transition duration-700 ease-out group-hover:scale-[1.04]" />
      </div>
      <div className={cn('flex flex-1 flex-col p-5 sm:p-6', lead && 'sm:justify-center lg:p-8')}>
        <h3 className={cn('leading-tight font-black tracking-tight text-ink', lead ? 'text-2xl' : 'text-xl')}>{member.name}</h3>
        <p className={cn('mt-1.5 font-bold text-gold-600', lead ? 'text-base' : 'text-[15px] leading-snug')}>{member.position}</p>
        {member.bio ? (
          <p className={cn('mt-3 text-sm leading-6 text-muted', lead ? 'line-clamp-4' : 'line-clamp-3')}>{member.bio}</p>
        ) : null}
        {tags.length ? (
          <ul className="mt-4 flex flex-wrap gap-1.5" aria-label={t('team.profile.skills')}>
            {tags.map((tag) => <li key={tag} className="rounded-md bg-surface-purple px-2 py-0.5 text-xs font-semibold text-brand-700">{tag}</li>)}
          </ul>
        ) : null}
        <span className={cn('inline-flex items-center gap-1.5 pt-5 text-sm font-bold text-brand-700 transition group-hover:text-brand-900', lead ? 'sm:mt-2' : 'mt-auto')}>
          {t('cta.more')} <ArrowRight className="size-4 transition group-hover:translate-x-1" aria-hidden />
        </span>
      </div>
    </Link>
  )
}

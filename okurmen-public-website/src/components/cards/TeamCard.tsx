import { Briefcase } from 'lucide-react'

import { SmartImage } from '@/components/shared/SmartImage'
import { useI18n } from '@/i18n'
import type { TeamMember } from '@/types/api'

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase()
}

export function TeamCard({ member, detailed }: { member: TeamMember; detailed?: boolean }) {
  const { t } = useI18n()
  return (
    <article className="card group flex h-full flex-col overflow-hidden">
      <div className="relative aspect-[4/5] overflow-hidden bg-gradient-to-br from-brand-100 via-brand-50 to-gold-50">
        <SmartImage
          image={member.photo}
          alt={member.name}
          sizes="(min-width: 1024px) 25vw, 50vw"
          className="size-full object-top transition duration-700 group-hover:scale-105"
          fallback={<span className="font-display text-5xl font-black text-brand-300">{initials(member.name)}</span>}
        />
      </div>
      <div className="flex flex-1 flex-col p-5">
        <h3 className="text-lg leading-tight font-extrabold">{member.name}</h3>
        <p className="mt-1 text-sm font-bold text-gold-600">{member.position}</p>
        {member.specialization ? <p className="mt-2 text-sm text-ink-soft">{member.specialization}</p> : null}
        {detailed && member.bio ? <p className="mt-3 line-clamp-5 text-sm text-muted">{member.bio}</p> : null}
        {member.experience_years ? (
          <p className="mt-auto flex items-center gap-1.5 pt-4 text-xs font-bold text-muted">
            <Briefcase className="size-3.5" aria-hidden />
            {t('team.experience', { years: t('team.years', { count: member.experience_years }) })}
          </p>
        ) : null}
      </div>
    </article>
  )
}

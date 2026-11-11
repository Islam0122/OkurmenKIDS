import { Briefcase, Sparkles } from 'lucide-react'

import { Dialog } from '@/components/shared/Dialog'
import { useI18n } from '@/i18n'
import type { TeamMember } from '@/types/api'

import { TeamPhoto } from './TeamCard'

/** Full public profile (same API data as the card — nothing added). */
export function TeamMemberDialog({ member, onClose }: { member: TeamMember | null; onClose: () => void }) {
  const { t } = useI18n()
  return (
    <Dialog open={member !== null} onClose={onClose} title={member?.name ?? ''} description={member?.position}>
      {member ? (
        <div className="space-y-5">
          <div className="grid gap-5 sm:grid-cols-[11rem_1fr]">
            <div className="mx-auto aspect-[4/5] w-40 overflow-hidden rounded-2xl bg-gradient-to-br from-brand-100 to-gold-50 sm:w-full">
              <TeamPhoto member={member} sizes="176px" className="size-full object-top" />
            </div>
            <div className="space-y-3">
              {member.group ? (
                <span className="inline-flex rounded-full bg-brand-50 px-2.5 py-1 text-xs font-bold tracking-wide text-brand-600 uppercase">{t(`team.group.${member.group}`)}</span>
              ) : null}
              {member.specialization ? (
                <p className="flex items-start gap-2 text-sm font-semibold text-ink-soft"><Sparkles className="mt-0.5 size-4 shrink-0 text-gold-500" aria-hidden />{member.specialization}</p>
              ) : null}
              {member.experience_years ? (
                <p className="flex items-center gap-2 text-sm font-semibold text-ink-soft">
                  <Briefcase className="size-4 shrink-0 text-gold-500" aria-hidden />
                  {t('team.experience', { years: t('team.years', { count: member.experience_years }) })}
                </p>
              ) : null}
            </div>
          </div>
          {member.bio ? <p className="text-[15px] leading-relaxed whitespace-pre-line text-ink-soft">{member.bio}</p> : null}
        </div>
      ) : null}
    </Dialog>
  )
}

import { CalendarDays, Sparkles, ThumbsUp, Trophy, Users, type LucideIcon } from 'lucide-react'

import { Reveal } from '@/components/shared/Reveal'
import { useI18n } from '@/i18n'
import type { SiteSettings } from '@/types/api'
import { cn } from '@/utils/cn'

/** An icon that fits the label marketing typed (ru / ky / en); a neutral one otherwise. */
function iconFor(label: string): LucideIcon {
  if (/учен|студент|окуучу|student/i.test(label)) return Users
  if (/лет|год|жыл|year/i.test(label)) return CalendarDays
  if (/довер|ишен|trust|родител|ата-эне|parent/i.test(label)) return ThumbsUp
  if (/проект|долбоор|project|побед|award|жеңиш/i.test(label)) return Trophy
  return Sparkles
}

const COLS: Record<number, string> = { 1: '', 2: 'grid-cols-2', 3: 'grid-cols-3', 4: 'grid-cols-2 lg:grid-cols-4' }

/** Academy numbers — only what marketing entered in the CMS (Settings → stats). Nothing is typed in here. */
export function Stats({ stats, title }: { stats: SiteSettings['stats']; title?: string }) {
  const { t } = useI18n()
  if (!stats.length) return null
  const items = stats.slice(0, 4)
  return (
    <section aria-label={title || t('home.stats.title')} className="mx-auto w-full max-w-[1280px] px-4 py-4 sm:px-6 lg:px-8">
      <div className="relative overflow-hidden rounded-[1.75rem] bg-gradient-to-br from-kids-deep via-kids-primary to-[#3d1c93] px-5 py-8 text-white shadow-[0_30px_60px_-30px_rgb(37_16_95/0.7)] sm:px-8 lg:py-10">
        <div aria-hidden className="absolute -top-24 right-[-6rem] size-72 rounded-full bg-kids-yellow/15 blur-3xl" />
        <ul className={cn('relative grid gap-y-8', COLS[items.length])}>
          {items.map((stat, i) => {
            const Icon = iconFor(stat.label)
            return (
              <Reveal
                as="li"
                key={i}
                delay={i * 0.06}
                className={cn('flex flex-col items-center px-1.5 text-center sm:px-2', i > 0 && 'border-l border-white/15', items.length === 4 && i === 2 && 'max-lg:border-l-0')}
              >
                <Icon className="size-6 text-white/90 sm:size-8" strokeWidth={1.75} aria-hidden />
                <p className="mt-2.5 font-display text-[1.75rem] leading-none font-black text-kids-yellow sm:mt-3 sm:text-5xl">{stat.value}</p>
                <p className="mt-2 text-[13px] leading-tight font-semibold text-white sm:text-base">{stat.label}</p>
              </Reveal>
            )
          })}
        </ul>
      </div>
    </section>
  )
}

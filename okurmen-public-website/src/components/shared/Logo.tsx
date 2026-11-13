import { Link } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { BRAND } from '@/app/config/site'
import { useI18n } from '@/i18n'
import { cn } from '@/utils/cn'

/** The original logo (unchanged) with the «OKURMEN Kids» wordmark — the only public brand name. */
export function Logo({ className, inverted }: { className?: string; inverted?: boolean }) {
  const { path, t } = useI18n()
  return (
    <Link to={path('/')} className={cn('group flex items-center gap-2.5', className)} aria-label={`${BRAND.name} — ${t('nav.home')}`}>
      <span className="grid size-12 shrink-0 place-items-center overflow-hidden rounded-full bg-white shadow-soft ring-1 ring-line transition group-hover:scale-105">
        <img src={logo} alt="" width={48} height={43} className="size-[115%] max-w-none object-contain" />
      </span>
      <span className="leading-none">
        <span className={cn('block font-display text-[17px] font-black tracking-tight', inverted ? 'text-white' : 'text-brand-800')}>Okurmen</span>
        <span className={cn('mt-1 block text-xs font-bold tracking-[0.2em] uppercase', inverted ? 'text-gold-300' : 'text-gold-600')}>Kids</span>
      </span>
    </Link>
  )
}

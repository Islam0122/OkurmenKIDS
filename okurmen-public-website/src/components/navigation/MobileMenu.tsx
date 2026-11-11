import { AnimatePresence, motion } from 'framer-motion'
import { ArrowUpRight, Phone, X } from 'lucide-react'
import { useEffect } from 'react'
import { NavLink } from 'react-router-dom'

import { NAV } from '@/app/config/site'
import { Logo } from '@/components/shared/Logo'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { useSettings } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import { cn } from '@/utils/cn'
import { telHref } from '@/utils/format'

import { LanguageSwitcher } from './LanguageSwitcher'

/** Full-height phone menu: large touch targets, all ten sections, language, CTA. */
export function MobileMenu({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, path } = useI18n()
  const settings = useSettings()
  const phone = settings.data?.contacts.phone

  useEffect(() => {
    if (!open) return
    document.body.style.overflow = 'hidden'
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = ''
      document.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open ? (
        <motion.div className="fixed inset-0 z-[60] xl:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-brand-950/50 backdrop-blur-sm" onClick={onClose} aria-hidden />
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label={t('nav.menu')}
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="absolute inset-y-0 right-0 flex w-full max-w-sm flex-col bg-white shadow-lift"
          >
            <div className="flex h-[72px] items-center justify-between border-b border-line px-4">
              <Logo />
              <button type="button" onClick={onClose} className="grid size-11 place-items-center rounded-full hover:bg-brand-50" aria-label={t('nav.close')}>
                <X className="size-6" aria-hidden />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label={t('nav.menu')}>
              <ul className="space-y-1">
                {NAV.map((item, i) => (
                  <motion.li key={item.path} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.03 * i }}>
                    <NavLink to={path(item.path)} end={item.path === '/'} onClick={onClose}
                      className={({ isActive }) => cn('flex min-h-13 items-center gap-3 rounded-2xl px-4 text-base font-bold', isActive ? 'bg-brand-50 text-brand-800' : 'text-ink-soft active:bg-surface-soft')}>
                      <span className="grid size-9 place-items-center rounded-xl bg-surface-soft text-brand-500">
                        <item.icon className="size-[18px]" aria-hidden />
                      </span>
                      {t(item.label)}
                    </NavLink>
                  </motion.li>
                ))}
              </ul>
              <div className="mt-6 px-1">
                <p className="mb-2 text-xs font-bold tracking-wide text-muted uppercase">{t('nav.language')}</p>
                <LanguageSwitcher variant="inline" />
              </div>
            </nav>
            <div className="space-y-3 border-t border-line p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
              <EnrollButton size="lg" className="w-full" />
              {phone ? (
                <a href={telHref(phone)} className="flex h-12 items-center justify-center gap-2 rounded-full border border-line font-bold text-brand-800">
                  <Phone className="size-4" aria-hidden /> {phone}
                  <ArrowUpRight className="size-4 text-muted" aria-hidden />
                </a>
              ) : null}
            </div>
          </motion.aside>
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}

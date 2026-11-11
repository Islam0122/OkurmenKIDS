import { Check, ChevronDown, Globe } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { LANG_LABEL, LANG_SHORT, LANGS, localizedPath, splitLangPath, useI18n } from '@/i18n'
import { cn } from '@/utils/cn'

/** Switches the URL prefix (/, /ky, /en) and keeps the current page and query. */
export function LanguageSwitcher({ variant = 'menu' }: { variant?: 'menu' | 'inline' }) {
  const { lang, t } = useI18n()
  const location = useLocation()
  const { rest } = splitLangPath(location.pathname)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const href = (code: (typeof LANGS)[number]) => `${localizedPath(code, rest)}${location.search}`

  if (variant === 'inline') {
    return (
      <div className="grid grid-cols-3 gap-2" role="group" aria-label={t('nav.language')}>
        {LANGS.map((code) => (
          <Link key={code} to={href(code)} hrefLang={code} lang={code} aria-current={code === lang ? 'true' : undefined}
            className={cn('flex h-12 items-center justify-center rounded-xl border text-sm font-bold', code === lang ? 'border-brand-800 bg-brand-800 text-white' : 'border-line text-ink-soft')}>
            {LANG_LABEL[code]}
          </Link>
        ))}
      </div>
    )
  }

  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-haspopup="menu" aria-label={`${t('nav.language')}: ${LANG_LABEL[lang]}`}
        className="flex h-10 items-center gap-1.5 rounded-full px-3 text-sm font-bold text-brand-800 transition hover:bg-brand-50">
        <Globe className="size-4" aria-hidden />
        {LANG_SHORT[lang]}
        <ChevronDown className={cn('size-3.5 transition', open && 'rotate-180')} aria-hidden />
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 mt-2 w-44 overflow-hidden rounded-2xl border border-line bg-white p-1.5 shadow-lift">
          {LANGS.map((code) => (
            <Link key={code} role="menuitem" to={href(code)} hrefLang={code} lang={code} onClick={() => setOpen(false)}
              className={cn('flex items-center justify-between rounded-xl px-3 py-2.5 text-sm font-semibold hover:bg-brand-50', code === lang ? 'text-brand-800' : 'text-ink-soft')}>
              {LANG_LABEL[code]}
              {code === lang ? <Check className="size-4 text-gold-500" aria-hidden /> : null}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  )
}

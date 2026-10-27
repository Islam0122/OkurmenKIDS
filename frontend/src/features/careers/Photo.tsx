import { useState, type ReactNode } from 'react'

import { cn } from '@/utils/cn'

import { photo, type PhotoSlot } from './photos'

type Tone = 'indigo' | 'amber' | 'paper'

const TONE: Record<Tone, { bg: string; stroke: string; text: string }> = {
  indigo: { bg: 'bg-ok-indigo', stroke: 'var(--color-ok-amber)', text: 'text-white' },
  amber: { bg: 'bg-ok-amber', stroke: 'var(--color-ok-indigo)', text: 'text-ok-indigo-deep' },
  paper: { bg: 'bg-ok-indigo-50', stroke: 'var(--color-ok-indigo)', text: 'text-ok-indigo' },
}

/** Мотив логотипа — «очки» с бровями — крупно и с обрезкой краем кадра. */
export function GlassesMark({ stroke, className }: { stroke: string; className?: string }) {
  return (
    <svg viewBox="0 0 240 120" fill="none" aria-hidden className={className}>
      <path d="M22 34 C40 22 70 20 92 28" stroke={stroke} strokeWidth="7" strokeLinecap="round" />
      <path d="M148 18 C170 12 200 18 218 34" stroke={stroke} strokeWidth="9" strokeLinecap="round" />
      <rect x="18" y="48" width="86" height="54" rx="12" stroke={stroke} strokeWidth="6" />
      <rect x="136" y="48" width="86" height="54" rx="12" stroke={stroke} strokeWidth="6" />
      <path d="M104 70 H136" stroke={stroke} strokeWidth="6" strokeLinecap="round" />
    </svg>
  )
}

/** Фирменная иллюстрация вместо фотографии, пока снимка нет (или он не
 * загрузился). `motif` — мотив очков из логотипа (крупно, с обрезкой краем);
 * подпись — сверху или снизу, чтобы не спорить с соседними блоками. */
export function BrandPanel({ tone = 'indigo', motif = true, textAt = 'bottom', label, children, className }: {
  tone?: Tone
  motif?: boolean
  textAt?: 'top' | 'bottom'
  label?: string
  children?: ReactNode
  className?: string
}) {
  const t = TONE[tone]
  return (
    <div className={cn('relative isolate flex h-full w-full overflow-hidden', textAt === 'top' ? 'items-start' : 'items-end', t.bg, t.text, className)}
      role={label ? 'img' : undefined} aria-label={label}>
      {motif ? (
        <GlassesMark stroke={t.stroke}
          className={cn('absolute w-[92%] opacity-90', textAt === 'top' ? '-right-[22%] bottom-[10%]' : '-right-[18%] top-[12%]')} />
      ) : null}
      <div className="absolute inset-0 -z-10 opacity-[0.12]" style={{ backgroundImage: `radial-gradient(${t.stroke} 1px, transparent 1px)`, backgroundSize: '18px 18px' }} />
      {children ? <div className="relative w-full p-6 sm:p-8">{children}</div> : null}
    </div>
  )
}

/** Фото слота с фиксированным соотношением сторон (без сдвига вёрстки).
 * Первый экран грузится сразу (`priority`), остальное — лениво. */
export function Photo({ slot, className, priority = false, tone, motif, textAt, fallback, sizes }: {
  slot: PhotoSlot
  className?: string
  priority?: boolean
  tone?: Tone
  motif?: boolean
  textAt?: 'top' | 'bottom'
  fallback?: ReactNode
  sizes?: string
}) {
  const { src, alt } = photo(slot)
  const [failed, setFailed] = useState(false)
  return (
    <div className={cn('relative overflow-hidden bg-ok-indigo-50', className)}>
      {src && !failed ? (
        <img
          src={src}
          alt={alt}
          sizes={sizes}
          loading={priority ? 'eager' : 'lazy'}
          decoding={priority ? 'sync' : 'async'}
          fetchPriority={priority ? 'high' : 'auto'}
          onError={() => setFailed(true)}
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <BrandPanel tone={tone} motif={motif} textAt={textAt} className="absolute inset-0">{fallback}</BrandPanel>
      )}
    </div>
  )
}

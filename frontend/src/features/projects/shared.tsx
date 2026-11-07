import { FolderKanban, Star } from 'lucide-react'
import { useLocation } from 'react-router-dom'

import { resolveMediaUrl } from '@/lib/mediaUrl'
import type { ProjectStatus } from '@/types/projects'
import { cn } from '@/utils/cn'

/** The trainer cabinet (/trainer/projects) and the read-only operations
 * cabinet (/operations/academy/projects) render the same pages. */
export function useProjectsBase(): string {
  const { pathname } = useLocation()
  return pathname.startsWith('/operations') ? '/operations/academy/projects' : '/trainer/projects'
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '?'
}

/** A stable, soft tint per person, so the same student always reads the same. */
const AVATAR_TINTS = [
  'bg-brand-50 text-brand-700',
  'bg-info-soft text-info',
  'bg-warning-soft text-warning',
  'bg-[#f1ecfb] text-[#5b3fa8]',
  'bg-[#e8f4f6] text-[#1f6b78]',
  'bg-[#fbeef3] text-[#a33a66]',
]

function tintFor(seed: number | string): string {
  const n = typeof seed === 'number' ? seed : [...seed].reduce((sum, ch) => sum + ch.charCodeAt(0), 0)
  return AVATAR_TINTS[Math.abs(n) % AVATAR_TINTS.length]
}

export interface AvatarProps {
  name: string
  seed?: number | string
  image?: string | null
  size?: 'xs' | 'sm' | 'md' | 'lg'
  className?: string
}

const AVATAR_SIZES = { xs: 'size-6 text-[10px]', sm: 'size-8 text-xs', md: 'size-10 text-sm', lg: 'size-14 text-base' } as const

export function Avatar({ name, seed, image, size = 'sm', className }: AvatarProps) {
  const src = resolveMediaUrl(image)
  if (src) {
    return <img src={src} alt="" className={cn('shrink-0 rounded-full object-cover', AVATAR_SIZES[size], className)} />
  }
  return (
    <span
      aria-hidden
      className={cn('inline-flex shrink-0 items-center justify-center rounded-full font-semibold', AVATAR_SIZES[size], tintFor(seed ?? name), className)}
    >
      {initials(name)}
    </span>
  )
}

export function TechTag({ name, className }: { name: string; className?: string }) {
  return (
    <span className={cn('inline-flex h-6 items-center rounded-md border border-border bg-surface-muted px-2 text-xs font-medium text-ink-secondary', className)}>
      {name}
    </span>
  )
}

export function StatusPill({ status, className }: { status: ProjectStatus; className?: string }) {
  const published = status === 'published'
  return (
    <span
      className={cn(
        'inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium',
        published ? 'bg-brand-50 text-brand-700' : 'bg-surface-hover text-ink-secondary ring-1 ring-inset ring-border',
        className,
      )}
    >
      <span className={cn('size-1.5 rounded-full', published ? 'bg-brand-500' : 'bg-ink-muted')} aria-hidden />
      {published ? 'Опубликован' : 'Черновик'}
    </span>
  )
}

export function RatingStars({ value, size = 'sm' }: { value: number; size?: 'sm' | 'md' }) {
  return (
    <span className="inline-flex items-center gap-0.5" role="img" aria-label={`Оценка ${value} из 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Star
          key={n}
          aria-hidden
          className={cn(size === 'md' ? 'size-5' : 'size-3.5', n <= value ? 'fill-warning text-warning' : 'fill-transparent text-border-strong')}
        />
      ))}
    </span>
  )
}

/** Cover placeholder for a project without images. */
export function CoverPlaceholder({ title, className }: { title: string; className?: string }) {
  return (
    <div className={cn('flex size-full flex-col items-center justify-center gap-2 bg-brand-50/60 text-brand-600', className)}>
      <FolderKanban className="size-8 opacity-70" aria-hidden />
      <span className="max-w-[80%] truncate px-2 text-xs font-medium text-ink-muted">{title}</span>
    </div>
  )
}

export function ProjectCover({ url, title, className, imgClassName }: { url: string | null; title: string; className?: string; imgClassName?: string }) {
  const src = resolveMediaUrl(url)
  return (
    <div className={cn('overflow-hidden bg-surface-muted', className)}>
      {src ? (
        <img src={src} alt={`Обложка проекта «${title}»`} loading="lazy" className={cn('size-full object-cover', imgClassName)} />
      ) : (
        <CoverPlaceholder title={title} />
      )}
    </div>
  )
}

/** Friendly empty-gallery illustration (decorative inline SVG — no assets). */
export function ProjectsIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 140" fill="none" aria-hidden className={className}>
      <rect x="22" y="30" width="96" height="74" rx="10" className="fill-surface stroke-border" strokeWidth="2" />
      <rect x="30" y="38" width="80" height="40" rx="6" className="fill-brand-50" />
      <path d="M38 72l16-16 12 12 8-8 16 12" className="stroke-brand-500" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="94" cy="50" r="5" className="fill-brand-200" />
      <rect x="30" y="85" width="44" height="6" rx="3" className="fill-border" />
      <rect x="30" y="95" width="28" height="4" rx="2" className="fill-border" />
      <rect x="82" y="44" width="96" height="74" rx="10" className="fill-surface stroke-border-strong" strokeWidth="2" />
      <rect x="90" y="52" width="80" height="40" rx="6" className="fill-surface-hover" />
      <path d="M118 72h24M130 60v24" className="stroke-brand-600" strokeWidth="3.5" strokeLinecap="round" />
      <rect x="90" y="99" width="50" height="6" rx="3" className="fill-border" />
      <rect x="90" y="109" width="32" height="4" rx="2" className="fill-border" />
      <circle cx="170" cy="28" r="4" className="fill-brand-200" />
      <circle cx="16" cy="112" r="3" className="fill-brand-100" />
      <path d="M160 14l2 5 5 2-5 2-2 5-2-5-5-2 5-2z" className="fill-brand-500" />
    </svg>
  )
}

export function ProjectCardSkeleton() {
  return (
    <div className="card animate-pulse overflow-hidden" aria-hidden>
      <div className="aspect-[16/10] bg-surface-hover" />
      <div className="space-y-3 p-4">
        <div className="h-4 w-2/3 rounded bg-surface-hover" />
        <div className="flex items-center gap-2">
          <div className="size-6 rounded-full bg-surface-hover" />
          <div className="h-3 w-1/3 rounded bg-surface-hover" />
        </div>
        <div className="flex gap-1.5">
          <div className="h-5 w-14 rounded bg-surface-hover" />
          <div className="h-5 w-16 rounded bg-surface-hover" />
        </div>
        <div className="h-3 w-5/6 rounded bg-surface-hover" />
      </div>
    </div>
  )
}

export function ProjectRowSkeleton() {
  return (
    <div className="flex animate-pulse items-center gap-4 px-4 py-3" aria-hidden>
      <div className="h-14 w-20 shrink-0 rounded-lg bg-surface-hover" />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="h-4 w-1/3 rounded bg-surface-hover" />
        <div className="h-3 w-1/4 rounded bg-surface-hover" />
      </div>
    </div>
  )
}

export const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024

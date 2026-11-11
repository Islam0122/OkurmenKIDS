import { useState } from 'react'
import { ImageOff } from 'lucide-react'

import type { ImageAsset } from '@/types/api'
import { cn } from '@/utils/cn'
import { mediaUrl } from '@/utils/media'

interface Props {
  image?: ImageAsset | null
  /** A plain URL (student projects return only `cover_url`). */
  src?: string | null
  alt: string
  className?: string
  /** CSS sizes hint for srcset, e.g. "(min-width: 1024px) 33vw, 100vw". */
  sizes?: string
  priority?: boolean
  fallback?: React.ReactNode
}

/**
 * Lazy, responsive image: the backend's WebP «thumb» (≤640px) and «large»
 * (≤1600px) copies become a srcset; width/height reserve space (no layout
 * shift). A soft brand placeholder shows while loading and on error.
 */
export function SmartImage({ image, src, alt, className, sizes = '(min-width: 1024px) 33vw, 100vw', priority, fallback }: Props) {
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)
  const full = mediaUrl(image?.url ?? src)
  const thumb = mediaUrl(image?.thumb)
  const srcSet = thumb && full && thumb !== full ? `${thumb} 640w, ${full} 1600w` : undefined

  if (!full || failed) {
    return (
      <div className={cn('flex items-center justify-center bg-gradient-to-br from-brand-50 to-surface-soft text-brand-300', className)} role="img" aria-label={alt}>
        {fallback ?? <ImageOff className="size-8" aria-hidden />}
      </div>
    )
  }
  return (
    <img
      src={srcSet ? thumb : full}
      srcSet={srcSet}
      sizes={srcSet ? sizes : undefined}
      alt={alt}
      width={image?.width ?? undefined}
      height={image?.height ?? undefined}
      loading={priority ? 'eager' : 'lazy'}
      decoding={priority ? 'sync' : 'async'}
      fetchPriority={priority ? 'high' : undefined}
      onLoad={() => setLoaded(true)}
      onError={() => setFailed(true)}
      className={cn('bg-brand-50 object-cover transition-opacity duration-500', loaded ? 'opacity-100' : 'opacity-0', className)}
    />
  )
}

import { ImageIcon } from 'lucide-react'

import type { NewsImage as NewsImageData } from '@/api/publicNews'
import { resolveMediaUrl } from '@/lib/mediaUrl'
import { cn } from '@/utils/cn'

interface Props {
  image: NewsImageData | null
  /** `sizes` for the browser to pick the 640 px or the 1600 px copy. */
  sizes: string
  className?: string
  /** Above the fold: load at once. */
  priority?: boolean
  alt?: string
}

/** A news photo: WebP 640/1600 srcset, reserved size, lazy unless `priority`. */
export function NewsImage({ image, sizes, className, priority = false, alt = '' }: Props) {
  const full = resolveMediaUrl(image?.url)
  const thumb = resolveMediaUrl(image?.thumb)
  if (!image || !full) {
    return (
      <div className={cn('flex size-full items-center justify-center bg-gradient-to-br from-pd-green-soft to-white', className)}>
        <span className="grid size-14 place-items-center rounded-2xl border border-pd-green-line bg-white text-pd-green pd-shadow">
          <ImageIcon className="size-6" strokeWidth={1.75} aria-hidden />
        </span>
      </div>
    )
  }
  return (
    <img
      src={full}
      srcSet={thumb && thumb !== full ? `${thumb} 640w, ${full} 1600w` : undefined}
      sizes={sizes}
      width={image.width ?? undefined}
      height={image.height ?? undefined}
      alt={alt}
      loading={priority ? 'eager' : 'lazy'}
      decoding="async"
      fetchPriority={priority ? 'high' : undefined}
      className={cn('size-full object-cover', className)}
    />
  )
}

import { Maximize2 } from 'lucide-react'

import type { NewsImage as NewsImageData } from '@/api/publicNews'
import { useI18n } from '@/features/portal/i18n'
import { resolveMediaUrl } from '@/lib/mediaUrl'

interface Props {
  photos: NewsImageData[]
  /** Index of the first photo in the lightbox list (the cover comes before). */
  offset: number
  onOpen: (index: number) => void
}

/** Masonry of photos in their own proportions — portrait and landscape side by
 * side; thumbnails lazy-load, each opens full size with its caption. */
export function PhotoGallery({ photos, offset, onOpen }: Props) {
  const { t } = useI18n()
  const n = t.news
  return (
    <ul className="columns-1 gap-4 sm:columns-2 lg:columns-3 [&>li]:mb-4">
      {photos.map((photo, index) => {
        const src = resolveMediaUrl(photo.thumb)
        const ratio = photo.width && photo.height ? `${photo.width} / ${photo.height}` : '4 / 3'
        return (
          <li key={`${photo.url}-${index}`} className="break-inside-avoid">
            <figure>
              <button
                type="button"
                onClick={() => onOpen(offset + index)}
                aria-label={photo.caption ? `${n.open(offset + index + 1)}: ${photo.caption}` : n.open(offset + index + 1)}
                className="group relative block w-full overflow-hidden rounded-2xl border border-pd-line bg-pd-subtle pd-shadow outline-none transition hover:pd-shadow-lg focus-visible:ring-4 focus-visible:ring-pd-green/20"
                style={{ aspectRatio: ratio }}
              >
                {src ? (
                  <img src={src} alt={photo.caption} loading="lazy" decoding="async" width={photo.width ?? undefined} height={photo.height ?? undefined}
                    className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.03]" />
                ) : null}
                <span className="absolute right-2.5 top-2.5 grid size-8 place-items-center rounded-full bg-zinc-950/55 text-white opacity-0 backdrop-blur transition group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden>
                  <Maximize2 className="size-4" />
                </span>
              </button>
              {photo.caption ? <figcaption className="mt-2 px-1 text-sm leading-snug text-pd-muted">{photo.caption}</figcaption> : null}
            </figure>
          </li>
        )
      })}
    </ul>
  )
}

import { useEffect } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { PortalModal } from './PortalModal'

export interface LightboxImage {
  src: string
  caption?: string
  width?: number | null
  height?: number | null
}

interface LightboxProps {
  images: LightboxImage[]
  /** Open image, or null when closed. */
  index: number | null
  onIndex: (index: number | null) => void
  /** «Photo 2 of 5» */
  label: (index: number, total: number) => string
  prev: string
  next: string
}

/** Full-size photos: ← / → and the buttons move, Esc and a click outside close, Tab stays inside. */
export function Lightbox({ images, index, onIndex, label, prev, next }: LightboxProps) {
  const open = index !== null
  const count = images.length
  const current = Math.min(index ?? 0, Math.max(count - 1, 0))

  useEffect(() => {
    if (!open || count < 2) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'ArrowRight') onIndex((current + 1) % count)
      if (event.key === 'ArrowLeft') onIndex((current - 1 + count) % count)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, current, count, onIndex])

  // Warm the neighbours so the next click is instant.
  useEffect(() => {
    if (!open || count < 2) return
    for (const step of [1, -1]) {
      const image = new Image()
      image.src = images[(current + step + count) % count].src
    }
  }, [open, current, count, images])

  const image = images[current]
  const button =
    'inline-flex h-10 items-center justify-center gap-1.5 rounded-lg border border-pd-line bg-pd-panel px-3.5 text-sm font-semibold text-pd-ink pd-shadow transition hover:border-pd-green-line hover:text-pd-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pd-green'

  return (
    <PortalModal open={open && Boolean(image)} onClose={() => onIndex(null)} size="lg" title={label(current + 1, count)}>
      {image ? (
        <figure>
          <div className="overflow-hidden rounded-xl border border-pd-line bg-zinc-950/[0.03]">
            <img
              key={image.src}
              src={image.src}
              alt={image.caption || label(current + 1, count)}
              width={image.width ?? undefined}
              height={image.height ?? undefined}
              className="mx-auto max-h-[68dvh] w-auto object-contain"
            />
          </div>
          {image.caption ? <figcaption className="mt-3 text-center text-sm text-pd-muted">{image.caption}</figcaption> : null}
        </figure>
      ) : null}
      {count > 1 ? (
        <div className="mt-4 flex items-center justify-between gap-3">
          <button type="button" className={button} onClick={() => onIndex((current - 1 + count) % count)}>
            <ChevronLeft className="size-4" aria-hidden />
            {prev}
          </button>
          <span className="text-sm tabular-nums text-pd-faint">
            {current + 1} / {count}
          </span>
          <button type="button" className={button} onClick={() => onIndex((current + 1) % count)}>
            {next}
            <ChevronRight className="size-4" aria-hidden />
          </button>
        </div>
      ) : null}
    </PortalModal>
  )
}

import { AnimatePresence, motion } from 'framer-motion'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { SmartImage } from '@/components/shared/SmartImage'
import type { ImageAsset } from '@/types/api'
import { mediaUrl } from '@/utils/media'

/** Photo grid + keyboard / swipe friendly lightbox. */
export function Gallery({ photos, title }: { photos: ImageAsset[]; title: string }) {
  const [open, setOpen] = useState<number | null>(null)
  const close = useCallback(() => setOpen(null), [])
  const step = useCallback((delta: number) => setOpen((i) => (i === null ? i : (i + delta + photos.length) % photos.length)), [photos.length])

  useEffect(() => {
    if (open === null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
      if (e.key === 'ArrowRight') step(1)
      if (e.key === 'ArrowLeft') step(-1)
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, close, step])

  if (!photos.length) return null
  const current = open !== null ? photos[open] : null

  return (
    <>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4">
        {photos.map((photo, i) => (
          <li key={photo.url} className={i === 0 && photos.length > 4 ? 'col-span-2 row-span-2' : ''}>
            <button type="button" onClick={() => setOpen(i)} className="group block size-full overflow-hidden rounded-2xl" aria-label={photo.caption || `${title} — ${i + 1}`}>
              <SmartImage image={photo} alt={photo.caption || title} sizes="(min-width: 640px) 33vw, 50vw" className="aspect-square size-full transition duration-500 group-hover:scale-105" />
            </button>
          </li>
        ))}
      </ul>
      <AnimatePresence>
        {current ? (
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className="fixed inset-0 z-[80] flex items-center justify-center bg-brand-950/95 p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={close}
          >
            <button type="button" onClick={close} className="absolute top-4 right-4 grid size-12 place-items-center rounded-full bg-white/10 text-white hover:bg-white/20" aria-label="Close">
              <X className="size-6" aria-hidden />
            </button>
            {photos.length > 1 ? (
              <>
                <button type="button" onClick={(e) => { e.stopPropagation(); step(-1) }} className="absolute left-2 grid size-12 place-items-center rounded-full bg-white/10 text-white hover:bg-white/20 sm:left-6" aria-label="Previous">
                  <ChevronLeft className="size-6" aria-hidden />
                </button>
                <button type="button" onClick={(e) => { e.stopPropagation(); step(1) }} className="absolute right-2 grid size-12 place-items-center rounded-full bg-white/10 text-white hover:bg-white/20 sm:right-6" aria-label="Next">
                  <ChevronRight className="size-6" aria-hidden />
                </button>
              </>
            ) : null}
            <motion.figure key={current.url} initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="max-h-full max-w-5xl" onClick={(e) => e.stopPropagation()}>
              <img src={mediaUrl(current.url)} alt={current.caption || title} className="max-h-[80vh] w-auto rounded-xl object-contain" />
              <figcaption className="mt-3 text-center text-sm text-white/80">
                {current.caption} <span className="ml-2 text-white/50">{(open ?? 0) + 1} / {photos.length}</span>
              </figcaption>
            </motion.figure>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  )
}

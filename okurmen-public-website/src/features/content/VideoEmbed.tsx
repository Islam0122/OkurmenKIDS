import { Play } from 'lucide-react'
import { useState } from 'react'

import { cn } from '@/utils/cn'
import { youtubeThumb } from '@/utils/video'

/**
 * Click-to-load video: shows a poster first and loads the YouTube/Vimeo
 * iframe only when played — no third-party requests or cookies before that,
 * and a much faster page.
 */
export function VideoEmbed({ src, title = 'Video', className, poster }: { src: string; title?: string; className?: string; poster?: string | null }) {
  const [play, setPlay] = useState(false)
  const thumb = poster ?? youtubeThumb(src)
  return (
    <div className={cn('relative aspect-video overflow-hidden rounded-2xl bg-brand-900 shadow-lift', className)}>
      {play ? (
        <iframe
          src={`${src}${src.includes('?') ? '&' : '?'}autoplay=1&rel=0`}
          title={title}
          className="absolute inset-0 size-full"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowFullScreen
          loading="lazy"
        />
      ) : (
        <button type="button" onClick={() => setPlay(true)} className="group absolute inset-0 flex size-full items-center justify-center" aria-label={title}>
          {thumb ? <img src={thumb} alt="" loading="lazy" className="absolute inset-0 size-full object-cover opacity-80 transition group-hover:opacity-100" /> : null}
          <span className="absolute inset-0 bg-gradient-to-t from-brand-950/60 to-transparent" aria-hidden />
          <span className="relative grid size-20 place-items-center rounded-full bg-gold-400 text-brand-900 shadow-gold transition group-hover:scale-110">
            <Play className="ml-1 size-8 fill-current" aria-hidden />
          </span>
        </button>
      )}
    </div>
  )
}

import { Quote, Star } from 'lucide-react'

import { VideoEmbed } from '@/features/content/VideoEmbed'
import { SmartImage } from '@/components/shared/SmartImage'
import { useI18n } from '@/i18n'
import type { Testimonial } from '@/types/api'
import { mediaUrl } from '@/utils/media'

export function Stars({ rating }: { rating: number }) {
  const { t } = useI18n()
  return (
    <span className="flex gap-0.5" role="img" aria-label={t('testimonials.rating', { rating })}>
      {Array.from({ length: 5 }, (_, i) => (
        <Star key={i} className={i < rating ? 'size-4 fill-gold-400 text-gold-400' : 'size-4 text-line'} aria-hidden />
      ))}
    </span>
  )
}

export function TestimonialCard({ item }: { item: Testimonial }) {
  const { t } = useI18n()
  return (
    <figure className="card flex h-full flex-col p-6 sm:p-7">
      {item.video_embed ? <VideoEmbed src={item.video_embed} title={item.author_name} poster={mediaUrl(item.photo?.url)} className="mb-5" /> : null}
      <div className="flex items-center justify-between">
        <Quote className="size-8 fill-gold-200 text-gold-300" aria-hidden />
        {item.rating ? <Stars rating={item.rating} /> : null}
      </div>
      {item.text ? (
        <blockquote lang={item.language} className="mt-4 flex-1 text-[15px] leading-relaxed whitespace-pre-line text-ink-soft">{item.text}</blockquote>
      ) : <div className="flex-1" />}
      <figcaption className="mt-6 flex items-center gap-3 border-t border-line pt-5">
        {item.photo && !item.video_embed ? (
          <SmartImage image={item.photo} alt={item.author_name} sizes="48px" className="size-12 shrink-0 rounded-full" />
        ) : (
          <span className="grid size-12 shrink-0 place-items-center rounded-full bg-brand-50 font-display text-lg font-black text-brand-500">{item.author_name.charAt(0)}</span>
        )}
        <span>
          <span className="block font-bold text-ink">{item.author_name}</span>
          <span className="block text-sm text-muted">{t(`testimonials.role.${item.author_role}`)}{item.course ? ` · ${item.course}` : ''}</span>
        </span>
      </figcaption>
    </figure>
  )
}

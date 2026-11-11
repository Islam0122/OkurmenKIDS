import type { ReactNode } from 'react'

import { PageHero, type Crumb } from '@/components/shared/PageHero'
import { Reveal } from '@/components/shared/Reveal'
import { SmartImage } from '@/components/shared/SmartImage'
import { Gallery } from '@/features/content/Gallery'
import { RichText } from '@/features/content/RichText'
import { ShareButton } from '@/features/content/ShareButton'
import type { ImageAsset } from '@/types/api'

/** Shared layout of news articles, achievements and events. */
export function ArticleLayout({ title, lead, crumbs, meta, cover, body, photos, photosTitle, aside, related, preview }: {
  title: string
  lead?: string
  crumbs: Crumb[]
  meta?: ReactNode
  cover?: ImageAsset | null
  body: string
  photos: ImageAsset[]
  photosTitle: string
  aside?: ReactNode
  related?: ReactNode
  preview?: boolean
}) {
  return (
    <>
      <PageHero title={title} text={lead} crumbs={crumbs}>
        <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3 text-sm font-semibold text-ink-soft">
          {meta}
          {!preview ? <ShareButton title={title} /> : null}
        </div>
      </PageHero>
      <div className={aside ? 'container-page grid gap-10 py-12 lg:grid-cols-[1fr_360px] lg:py-16' : 'container-page py-12 lg:py-16'}>
        <article className={aside ? 'min-w-0' : 'mx-auto max-w-3xl'}>
          {cover ? (
            <Reveal as="div" className="mb-10">
              <figure>
                <SmartImage image={cover} alt={cover.caption || title} priority sizes="(min-width: 1024px) 60vw, 100vw" className="aspect-[16/9] w-full rounded-[2rem] shadow-soft" />
                {cover.caption ? <figcaption className="mt-3 text-center text-sm text-muted">{cover.caption}</figcaption> : null}
              </figure>
            </Reveal>
          ) : null}
          <RichText source={body} />
          {photos.length ? (
            <section className="mt-14">
              <h2 className="mb-6 text-2xl font-black">{photosTitle}</h2>
              <Gallery photos={photos} title={title} />
            </section>
          ) : null}
        </article>
        {aside ? <aside className="space-y-6 lg:sticky lg:top-28 lg:self-start">{aside}</aside> : null}
      </div>
      {related}
    </>
  )
}

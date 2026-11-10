import { Reveal } from '@/components/shared/Reveal'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { VideoEmbed } from '@/features/content/VideoEmbed'
import { useI18n } from '@/i18n'

export function IntroVideo({ src, title }: { src: string | null; title?: string }) {
  const { t } = useI18n()
  if (!src) return null
  return (
    <section className="section bg-surface-soft">
      <div className="container-page">
        <SectionHeader align="center" title={title || t('home.video.title')} text={t('home.video.text')} />
        <Reveal className="mx-auto max-w-4xl">
          <VideoEmbed src={src} title={title || t('home.video.title')} />
        </Reveal>
      </div>
    </section>
  )
}

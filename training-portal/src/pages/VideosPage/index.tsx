import { useState } from 'react'

import type { Video } from '@/types'

import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { VideoCard, VideoPlayerModal } from '@/components/VideoCard'
import { useAsync } from '@/hooks/useAsync'
import { t } from '@/i18n'
import { contentService } from '@/services/contentService'

export function VideosPage() {
  const { data, loading } = useAsync(() => contentService.getVideos())
  const [category, setCategory] = useState<string | null>(null)
  const [playing, setPlaying] = useState<Video | null>(null)
  const videos = data ?? []
  const categories = [...new Set(videos.map((v) => v.category).filter(Boolean))] as string[]
  const shown = category ? videos.filter((v) => v.category === category) : videos

  return (
    <div className="container" style={{ paddingBottom: 80 }}>
      <header className="page-head">
        <span className="eyebrow"><Icon name="camera-video" />{t.nav.videos}</span>
        <h1 className="page-title" style={{ marginTop: 14 }}>{t.videos.title}</h1>
        <p className="section-subtitle">{t.videos.subtitle}</p>
      </header>
      {categories.length > 1 ? (
        <div className="chips">
          <button type="button" className={`chip${!category ? ' is-active' : ''}`} onClick={() => setCategory(null)}>{t.videos.all}</button>
          {categories.map((c) => (
            <button key={c} type="button" className={`chip${category === c ? ' is-active' : ''}`} onClick={() => setCategory(c)}>{c}</button>
          ))}
        </div>
      ) : null}
      {loading ? <Loader /> : shown.length ? (
        <div className="grid-cards">{shown.map((video) => <VideoCard key={video.id} video={video} onPlay={setPlaying} />)}</div>
      ) : (
        <div className="empty"><Icon name="camera-video-off" /><p>{t.videos.empty}</p></div>
      )}
      <VideoPlayerModal video={playing} onClose={() => setPlaying(null)} />
    </div>
  )
}

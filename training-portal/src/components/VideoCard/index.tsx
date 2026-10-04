import { useState } from 'react'

import type { Video } from '@/types'

import { t } from '@/i18n'
import { parseVideoUrl } from '@/lib/video'

import { Button } from '../Button'
import { Icon } from '../Icon'
import { Modal } from '../Modal'
import './VideoCard.css'

/** Plays a YouTube / Vimeo / direct video in a modal; other links open outside. */
export function VideoPlayerModal({ video, onClose }: { video: Video | null; onClose: () => void }) {
  const source = video ? parseVideoUrl(video.video_url) : null
  return (
    <Modal open={Boolean(video)} onClose={onClose} title={video?.title ?? ''} width={880}>
      {source && video ? (
        source.kind === 'youtube' || source.kind === 'vimeo' ? (
          <div className="player">
            <iframe src={source.embedUrl} title={video.title} allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowFullScreen />
          </div>
        ) : source.kind === 'file' ? (
          <div className="player"><video src={source.src} controls autoPlay /></div>
        ) : (
          <div className="modal__actions">
            <Button href={source.href} newTab iconEnd="box-arrow-up-right">{t.videos.openExternal}</Button>
          </div>
        )
      ) : null}
      {video?.description ? <p className="modal__text">{video.description}</p> : null}
    </Modal>
  )
}

export function VideoCard({ video, onPlay }: { video: Video; onPlay: (video: Video) => void }) {
  const source = parseVideoUrl(video.video_url)
  const thumbnail = video.thumbnail_url || source.thumbnail
  const [broken, setBroken] = useState(false)
  return (
    <article className="video-card">
      <button type="button" className="video-card__thumb" onClick={() => onPlay(video)} aria-label={`${t.videos.watch}: ${video.title}`}>
        {thumbnail && !broken
          ? <img src={thumbnail} alt="" loading="lazy" onError={() => setBroken(true)} />
          : <span className="video-card__fallback"><Icon name="camera-video" /></span>}
        <span className="video-card__play"><Icon name="play-fill" /></span>
        {video.duration ? <span className="video-card__duration">{video.duration}</span> : null}
      </button>
      <div className="video-card__body">
        {video.category ? <span className="video-card__cat">{video.category}</span> : null}
        <h3 className="video-card__title">{video.title}</h3>
        {video.description ? <p className="video-card__desc">{video.description}</p> : null}
        <div className="video-card__foot">
          <Button variant="outline" size="sm" icon="play-circle" onClick={() => onPlay(video)}>{t.videos.watch}</Button>
        </div>
      </div>
    </article>
  )
}

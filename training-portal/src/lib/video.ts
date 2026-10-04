/** What kind of player a video URL needs, and its embed URL. */
export type VideoSource =
  | { kind: 'youtube'; id: string; embedUrl: string; thumbnail: string }
  | { kind: 'vimeo'; id: string; embedUrl: string; thumbnail?: undefined }
  | { kind: 'file'; src: string; thumbnail?: undefined }
  | { kind: 'external'; href: string; thumbnail?: undefined }

const YOUTUBE = /(?:youtube\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/)|youtu\.be\/)([\w-]{11})/
const VIMEO = /vimeo\.com\/(?:video\/)?(\d+)/
const VIDEO_FILE = /\.(mp4|webm|ogg|m4v)(\?|#|$)/i

export function parseVideoUrl(url: string): VideoSource {
  const youtube = url.match(YOUTUBE)
  if (youtube) {
    const id = youtube[1]
    return {
      kind: 'youtube',
      id,
      embedUrl: `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0`,
      thumbnail: `https://i.ytimg.com/vi/${id}/hqdefault.jpg`,
    }
  }
  const vimeo = url.match(VIMEO)
  if (vimeo) return { kind: 'vimeo', id: vimeo[1], embedUrl: `https://player.vimeo.com/video/${vimeo[1]}?autoplay=1` }
  if (VIDEO_FILE.test(url)) return { kind: 'file', src: url }
  return { kind: 'external', href: url }
}

export function isExternalUrl(url: string): boolean {
  return /^https?:\/\//i.test(url)
}

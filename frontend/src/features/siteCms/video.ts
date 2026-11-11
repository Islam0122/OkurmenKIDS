const YOUTUBE = /^https?:\/\/(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/|live\/)|youtu\.be\/|youtube-nocookie\.com\/embed\/)([A-Za-z0-9_-]{11})/
const VIMEO = /^https?:\/\/(?:www\.|player\.)?vimeo\.com\/(?:video\/)?(\d{6,12})/

/** YouTube / Vimeo link → privacy-friendly embed URL (same rule as the backend). */
export function videoEmbed(url: string): string | null {
  const value = url.trim()
  const yt = value.match(YOUTUBE)
  if (yt) return `https://www.youtube-nocookie.com/embed/${yt[1]}`
  const vimeo = value.match(VIMEO)
  if (vimeo) return `https://player.vimeo.com/video/${vimeo[1]}`
  return null
}

export function youtubeThumb(embed: string): string | null {
  const id = embed.match(/embed\/([A-Za-z0-9_-]{11})/)?.[1]
  return id ? `https://i.ytimg.com/vi/${id}/hqdefault.jpg` : null
}

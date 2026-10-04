export interface Video {
  id: string
  title: string
  description?: string
  /** optional — YouTube thumbnails are derived from the URL */
  thumbnail?: string
  /** YouTube, Vimeo or a direct video file URL */
  url: string
  category?: string
  /** «12:30» */
  duration?: string
  order: number
  published: boolean
}

export interface UsefulLink {
  id: string
  title: string
  description?: string
  url: string
  category?: string
  /** Bootstrap Icons name without the «bi-» prefix, e.g. «filetype-py» */
  icon?: string
  order: number
  published: boolean
}

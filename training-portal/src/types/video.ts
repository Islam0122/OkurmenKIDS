/** GET /api/v1/training/videos/ */
export interface Video {
  id: number
  title: string
  description: string
  video_url: string
  thumbnail_url: string
  category: string
  duration: string
  order: number
}

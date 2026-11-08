import axios from 'axios'

import { API_BASE_URL } from '@/api/client'

/** A bare client: no auth header — public news never sends anyone's token. */
const publicClient = axios.create({ baseURL: API_BASE_URL })

export const NEWS_CATEGORIES = ['all', 'events', 'achievements', 'competitions', 'education', 'announcements', 'activities'] as const
export type NewsCategory = (typeof NEWS_CATEGORIES)[number]
export type ArticleCategory = Exclude<NewsCategory, 'all'>

/** A photo with its fast copies: `url` ≤ 1600 px, `thumb` ≤ 640 px (WebP), original size for layout. */
export interface NewsImage {
  url: string
  thumb: string
  width: number | null
  height: number | null
  caption: string
}

/** `GET /public/news/` card — the backend's closed whitelist (apps.academy_news.public). */
export interface NewsCard {
  slug: string
  title: string
  excerpt: string
  category: ArticleCategory
  published_at: string
  cover: NewsImage | null
  photo_count: number
}

export interface NewsArticle extends Omit<NewsCard, 'photo_count'> {
  body: string
  /** Only when the article allows showing its author. */
  author: string | null
  photos: NewsImage[]
  related: NewsCard[]
}

export interface NewsPage {
  count: number
  page: number
  page_size: number
  num_pages: number
  counts: Record<NewsCategory, number>
  /** First page without search/category only. */
  featured: NewsCard | null
  results: NewsCard[]
}

export interface NewsParams {
  q?: string
  category?: NewsCategory
  page?: number
  page_size?: number
}

function clean(params: object): Record<string, string | number> {
  return Object.fromEntries(Object.entries(params).filter(([key, v]) => v !== undefined && v !== null && v !== '' && !(key === 'category' && v === 'all')))
}

export const publicNewsApi = {
  list: (params: NewsParams) => publicClient.get<NewsPage>('/public/news/', { params: clean(params) }).then((r) => r.data),
  article: (slug: string) => publicClient.get<NewsArticle>(`/public/news/${encodeURIComponent(slug)}/`).then((r) => r.data),
}

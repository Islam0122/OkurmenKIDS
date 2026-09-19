export type NewsType = 'info' | 'important' | 'warning' | 'event'

export type NewsAudience = 'all' | 'selected'

/** `apps.news.serializers.NewsSerializer` — the Teacher-facing news feed. */
export interface News {
  id: number
  title: string
  text: string
  type: NewsType
  type_label: string
  audience: NewsAudience
  audience_label: string
  created_at: string
  expires_at: string | null
  is_read: boolean
}

export interface UnreadNewsCount {
  count: number
}

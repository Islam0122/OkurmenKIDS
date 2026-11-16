/** «Сообщество» — /api/v1/portal/students/<id>/community/ (family) and
 * /api/v1/community/ (staff moderation). Backend: apps.community. */

export type CommunityCategory = 'general' | 'review' | 'achievement' | 'project' | 'learning_progress' | 'news'
export type PostStatus = 'draft' | 'pending' | 'approved' | 'rejected' | 'hidden'
export type Audience = 'academy' | 'group'

export interface CommunityAuthor {
  type: 'student' | 'academy'
  student_id: number | null
  name: string
  first_name?: string
  group: { id: number; name: string } | null
  photo: string | null
}

export interface CommunityImage {
  id: number
  /** Signed, short-lived links (private storage). */
  thumb: string
  large: string
  width: number
  height: number
}

export interface CommunityPost {
  id: number
  category: CommunityCategory
  audience: Audience
  text: string
  project_url: string
  status: PostStatus
  is_announcement: boolean
  is_pinned: boolean
  created_at: string
  published_at: string | null
  edited_at: string | null
  author: CommunityAuthor
  group: { id: number; name: string } | null
  images: CommunityImage[]
  likes: number
  comments: number
  liked: boolean
  mine: boolean
  can_edit: boolean
  can_delete: boolean
  moderation?: { note: string; moderated_at: string | null; submitted_at: string | null; by?: string | null }
  website_consent?: boolean
  /** Staff: approved review with consent — may be published on the website. */
  website_eligible?: boolean
  // staff only
  open_reports?: number
  /** The website testimonial of this review (okurmenkids.com/testimonials). */
  website?: { testimonial_id: number; status: string; is_public: boolean; language: string } | null
  comment_list?: CommunityComment[]
  reports?: { id: number; reason: string; reason_display: string; details: string; status: string; created_at: string }[]
}

export interface CommunityComment {
  id: number
  parent: number | null
  status: 'visible' | 'hidden' | 'deleted'
  text: string
  author: CommunityAuthor | null
  created_at: string
  mine: boolean
  open_reports?: number
  replies?: CommunityComment[]
}

export interface CommunityFeedPage {
  count: number
  next: string | null
  previous: string | null
  results: CommunityPost[]
  pinned?: CommunityPost[]
}

export interface CommunitySummary {
  published: number
  pending: number
  drafts: number
  rejected: number
  unread: number
  can_post: boolean
}

export type CommunityNotificationKind = 'comment' | 'reply' | 'like' | 'approved' | 'rejected' | 'hidden'

export interface CommunityNotification {
  id: number
  kind: CommunityNotificationKind
  post_id: number | null
  comment_id: number | null
  actor: string
  note: string
  is_read: boolean
  created_at: string
  post_excerpt: string
}

export interface CommunityProfile {
  id: number
  first_name: string
  last_name: string
  name: string
  group: { id: number; name: string } | null
  photo: string | null
  badges: { code: string; date: string | null; params: Record<string, string | number | null> }[]
  posts_count: number
  likes_received: number
  projects: CommunityPost[]
  is_me: boolean
}

export type ReportReason = 'personal_info' | 'bullying' | 'inappropriate' | 'spam' | 'other'

export interface PostInput {
  text: string
  category: CommunityCategory
  audience: Audience
  project_url: string
  website_consent: boolean
  images: File[]
  remove_images?: number[]
  submit: boolean
}

export interface ModerationMeta {
  pending: number
  open_reports: number
  can_announce_academy: boolean
  can_send_to_website: boolean
  /** Approved reviews with the family's consent that are not on okurmenkids.com yet. */
  website_waiting?: number
  groups: { id: number; name: string }[]
}

export interface ModerationReport {
  id: number
  reason: ReportReason
  reason_display: string
  details: string
  status: 'open' | 'resolved' | 'dismissed'
  created_at: string
  post_id: number
  target: 'post' | 'comment'
  comment: CommunityComment | null
  post_excerpt: string
  reporter: string
}

import { apiClient } from '@/api/client'
import type {
  CommunityComment,
  CommunityFeedPage,
  CommunityNotification,
  CommunityPost,
  CommunityProfile,
  CommunitySummary,
  ModerationMeta,
  ModerationReport,
  PostInput,
  PostStatus,
  ReportReason,
} from '@/types/community'
import type { Paginated } from '@/types/common'

const s = (id: number) => `/portal/students/${id}/community`
const data = <T>(p: Promise<{ data: T }>) => p.then((r) => r.data)

function form(input: PostInput): FormData {
  const body = new FormData()
  body.append('text', input.text)
  body.append('category', input.category)
  body.append('audience', input.audience)
  body.append('project_url', input.project_url)
  body.append('website_consent', String(input.website_consent))
  body.append('submit', String(input.submit))
  input.images.forEach((file) => body.append('images', file))
  input.remove_images?.forEach((id) => body.append('remove_images', String(id)))
  return body
}

/** As the selected child of the family account. */
export const communityApi = {
  summary: (id: number) => data(apiClient.get<CommunitySummary>(`${s(id)}/summary/`)),
  feed: (id: number, page: number, category?: string) =>
    data(apiClient.get<CommunityFeedPage>(`${s(id)}/`, { params: { page, category: category || undefined } })),
  mine: (id: number, page: number) => data(apiClient.get<CommunityFeedPage>(`${s(id)}/mine/`, { params: { page } })),
  post: (id: number, postId: number) => data(apiClient.get<CommunityPost>(`${s(id)}/posts/${postId}/`)),
  create: (id: number, input: PostInput) => data(apiClient.post<CommunityPost>(`${s(id)}/`, form(input))),
  update: (id: number, postId: number, input: PostInput) =>
    data(apiClient.patch<CommunityPost>(`${s(id)}/posts/${postId}/`, form(input))),
  remove: (id: number, postId: number) => apiClient.delete(`${s(id)}/posts/${postId}/`),
  like: (id: number, postId: number, liked: boolean) =>
    data(apiClient.post<{ liked: boolean; likes: number }>(`${s(id)}/posts/${postId}/like/`, { liked })),
  comments: (id: number, postId: number) => data(apiClient.get<CommunityComment[]>(`${s(id)}/posts/${postId}/comments/`)),
  comment: (id: number, postId: number, text: string, parent?: number | null) =>
    data(apiClient.post<CommunityComment>(`${s(id)}/posts/${postId}/comments/`, { text, parent: parent ?? null })),
  deleteComment: (id: number, commentId: number) => apiClient.delete(`${s(id)}/comments/${commentId}/`),
  reportPost: (id: number, postId: number, reason: ReportReason, details: string) =>
    apiClient.post(`${s(id)}/posts/${postId}/report/`, { reason, details }),
  reportComment: (id: number, commentId: number, reason: ReportReason, details: string) =>
    apiClient.post(`${s(id)}/comments/${commentId}/report/`, { reason, details }),
  profile: (id: number, otherId: number) => data(apiClient.get<CommunityProfile>(`${s(id)}/profiles/${otherId}/`)),
  notifications: (id: number) =>
    data(apiClient.get<{ unread: number; results: CommunityNotification[] }>(`${s(id)}/notifications/`)),
  readNotifications: (id: number) => data(apiClient.post<{ unread: number }>(`${s(id)}/notifications/`, {})),
}

const M = '/community'

/** Staff moderation (admin, assistants, team leads; trainers — their groups). */
export const moderationApi = {
  meta: () => data(apiClient.get<ModerationMeta>(`${M}/meta/`)),
  posts: (status: PostStatus | 'all', page: number, q = '') =>
    data(apiClient.get<Paginated<CommunityPost>>(`${M}/posts/`, { params: { status, page, q: q || undefined } })),
  post: (postId: number) => data(apiClient.get<CommunityPost>(`${M}/posts/${postId}/`)),
  act: (postId: number, action: 'approve' | 'reject' | 'hide' | 'pin' | 'to-website', body: object = {}) =>
    data(apiClient.post<CommunityPost>(`${M}/posts/${postId}/${action}/`, body)),
  removeAnnouncement: (postId: number) => apiClient.delete(`${M}/posts/${postId}/`),
  announce: (input: { text: string; group: number | null; pinned: boolean; images: File[] }) => {
    const body = new FormData()
    body.append('text', input.text)
    if (input.group) body.append('group', String(input.group))
    body.append('pinned', String(input.pinned))
    input.images.forEach((file) => body.append('images', file))
    return data(apiClient.post<CommunityPost>(`${M}/announcements/`, body))
  },
  reports: (status: 'open' | 'resolved' | 'dismissed', page: number) =>
    data(apiClient.get<Paginated<ModerationReport>>(`${M}/reports/`, { params: { status, page } })),
  closeReport: (reportId: number, status: 'resolved' | 'dismissed') => apiClient.post(`${M}/reports/${reportId}/close/`, { status }),
  hideComment: (commentId: number, hidden: boolean) =>
    data(apiClient.post<CommunityComment>(`${M}/comments/${commentId}/hide/`, { hidden })),
}

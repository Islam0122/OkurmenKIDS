/** Кабинет маркетинга (backend: apps.marketing, /api/v1/marketing/). */

export interface Choice<T extends string = string> {
  value: T
  label: string
}

/** Только имя — контакты и персональные данные сотрудников API не отдаёт. */
export interface TeamMember {
  id: number
  full_name: string
}

export type ContentStatus = 'idea' | 'preparing' | 'review' | 'scheduled' | 'published'
export type Channel = 'instagram' | 'tiktok' | 'facebook' | 'telegram' | 'youtube' | 'whatsapp' | 'website' | 'other'
export type ContentFormat = 'post' | 'carousel' | 'reels' | 'stories' | 'video' | 'article' | 'other'
export type TaskStatus = 'todo' | 'in_progress' | 'done'
export type TaskPriority = 'low' | 'medium' | 'high'

/** `GET /marketing/meta/` */
export interface MarketingMeta {
  channels: Choice<Channel>[]
  formats: Choice<ContentFormat>[]
  content_statuses: Choice<ContentStatus>[]
  task_statuses: Choice<TaskStatus>[]
  priorities: Choice<TaskPriority>[]
  team: TeamMember[]
  me: number
  today: string
  /** Есть, когда бэкенд знает о кампаниях (apps.marketing.Campaign). */
  campaign_statuses?: Choice<CampaignStatus>[]
  can_view_budget?: boolean
}

export type CampaignStatus = 'planned' | 'active' | 'paused' | 'finished' | 'cancelled'

/** Рекламная кампания. Бюджет, расход и CPL сервер отдаёт только тем, кому
 * разрешены финансовые данные маркетинга. */
export interface Campaign {
  id: number
  name: string
  channel: Channel
  channel_label: string
  responsible: number | null
  responsible_info: TeamMember | null
  status: CampaignStatus
  status_label: string
  start_date: string
  end_date: string | null
  budget?: string
  spent?: string
  leads: number
  sales: number
  cost_per_lead?: string | null
  conversion: number | null
  result: string
  can_delete: boolean
}

export type CampaignInput = Partial<Pick<Campaign, 'name' | 'channel' | 'responsible' | 'status' | 'start_date' | 'end_date' | 'budget' | 'spent' | 'leads' | 'sales' | 'result'>>

export interface ContentItem {
  id: number
  title: string
  channel: Channel
  channel_label: string
  format: ContentFormat
  format_label: string
  publish_date: string | null
  /** `HH:MM:SS` */
  publish_time: string | null
  status: ContentStatus
  status_label: string
  responsible: number | null
  responsible_info: TeamMember | null
  description: string
  post_url: string
  published_at: string | null
  created_by_info: TeamMember | null
  created_at: string
  updated_at: string
  can_delete: boolean
}

export interface ContentInput {
  title: string
  channel: Channel
  format: ContentFormat
  publish_date: string | null
  publish_time: string | null
  status: ContentStatus
  responsible: number | null
  description: string
  post_url: string
}

export interface ContentParams {
  status?: string
  channel?: Channel
  responsible?: number
  mine?: '1'
  date_from?: string
  date_to?: string
  no_date?: '1'
  search?: string
  page?: number
  page_size?: number
}

export interface MarketingTask {
  id: number
  title: string
  description: string
  due_date: string | null
  priority: TaskPriority
  priority_label: string
  status: TaskStatus
  status_label: string
  is_overdue: boolean
  responsible: number | null
  responsible_info: TeamMember | null
  completed_at: string | null
  created_by_info: TeamMember | null
  created_at: string
  updated_at: string
  can_delete: boolean
}

export interface TaskInput {
  title: string
  description: string
  due_date: string | null
  priority: TaskPriority
  status: TaskStatus
  responsible: number | null
}

export type TaskStatusFilter = TaskStatus | 'open' | 'overdue'
export type TaskDueFilter = 'today' | 'week' | 'overdue' | 'none'

export interface TasksParams {
  status?: TaskStatusFilter
  priority?: TaskPriority
  responsible?: number
  mine?: '1'
  due?: TaskDueFilter
  search?: string
  page?: number
  page_size?: number
}

/** `GET /marketing/dashboard/` */
export interface MarketingDashboard {
  today: string
  period: { date_from: string; date_to: string }
  tasks: { open: number; in_progress: number; overdue: number; due_today: number; mine_open: number; done_in_period: number }
  content: { ideas: number; in_work: number; scheduled: number; planned_in_period: number; published_in_period: number }
  upcoming_tasks: MarketingTask[]
  upcoming_content: ContentItem[]
}

export type ReportPeriod = 'week' | 'month'

/** `GET /marketing/reports/?period=week|month&date=` */
export interface MarketingReport {
  period: { kind: ReportPeriod; date_from: string; date_to: string }
  today: string
  tasks: { created: number; completed: number; completed_on_time: number; completed_late: number; overdue_now: number; open_due_in_period: number }
  content: { planned: number; prepared: number; published: number; plan_due: number; plan_done: number; plan_completion: number | null }
  series: { date_from: string; date_to: string; published: number; planned: number; tasks_completed: number }[]
  by_channel: { channel: Channel; label: string; planned: number; published: number }[]
  by_person: { id: number; full_name: string; tasks_completed: number; tasks_open: number; content_planned: number; content_published: number }[]
}

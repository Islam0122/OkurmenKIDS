/** `apps.projects` — student projects registered by trainers. */
export type ProjectStatus = 'draft' | 'published'

export interface ProjectStudentRef {
  id: number
  full_name: string
  status: string
}

export interface ProjectRef {
  id: number
  name: string
}

export interface ProjectAuthor {
  id: number
  full_name: string
  image: string | null
}

export interface ProjectImage {
  id: number
  url: string | null
  is_cover: boolean
  order: number
}

/** `GET /projects/` row. */
export interface ProjectListItem {
  id: number
  title: string
  short_description: string
  project_date: string
  status: ProjectStatus
  rating: number | null
  technologies: string[]
  student: ProjectStudentRef
  group: ProjectRef | null
  author: ProjectAuthor | null
  cover_url: string | null
  images_count: number
  can_edit: boolean
  created_at: string
  updated_at: string
}

/** `GET /projects/{id}/` */
export interface ProjectDetail extends ProjectListItem {
  description: string
  github_url: string
  demo_url: string
  figma_url: string
  trainer_comment: string
  images: ProjectImage[]
  course: ProjectRef | null
}

/** `POST /projects/`, `PATCH /projects/{id}/` */
export interface ProjectInput {
  student: number
  title: string
  short_description: string
  description: string
  technologies: string[]
  project_date: string
  github_url: string
  demo_url: string
  figma_url: string
  trainer_comment: string
  rating: number | null
  status: ProjectStatus
}

/** `GET /projects/stats/` */
export interface ProjectStats {
  total_projects: number
  active_students: number
  projects_this_month: number
  projects_previous_month: number
  month_change_percent: number | null
  groups_with_projects: number
  drafts: number
}

export interface SelectableStudent {
  id: number
  full_name: string
  status: string
  group: ProjectRef | null
  projects_count: number
}

/** `GET /projects/options/` */
export interface ProjectOptions {
  can_create: boolean
  groups: ProjectRef[]
  students: { id: number; full_name: string }[]
  selectable_students: SelectableStudent[]
  technologies: string[]
  max_images: number
}

export interface ProjectFilters {
  q?: string
  group?: string
  student?: string
  technology?: string
  date_from?: string
  date_to?: string
  status?: ProjectStatus
  page?: number
}

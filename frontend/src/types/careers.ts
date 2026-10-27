/** Публичный карьерный сайт (`/api/v1/public/careers/`) — только поля для посетителя. */

export interface PublicSalary {
  min: number | null
  max: number | null
  currency: string
  currency_label: string
}

export interface PublicVacancyCard {
  slug: string
  title: string
  department: string
  location: string
  work_format: string
  work_format_label: string
  employment_type: string
  employment_type_label: string
  salary: PublicSalary | null
  summary: string
  published_at: string | null
  closes_on: string | null
  is_open: boolean
}

export interface PublicVacancy extends PublicVacancyCard {
  description: string
  responsibilities: string[]
  requirements: string[]
  nice_to_have: string[]
  conditions: string[]
  selection_stages: string[]
}

export interface PublicVacancyList {
  count: number
  page: number
  page_size: number
  results: PublicVacancyCard[]
}

export interface PublicOption {
  value: string
  label: string
}

export interface CareersFilters {
  total: number
  departments: string[]
  locations: string[]
  work_formats: PublicOption[]
  employment_types: PublicOption[]
  sources: PublicOption[]
  resume_max_mb: number
}

export type CareersOrdering = 'newest' | 'oldest' | 'salary_desc' | 'salary_asc' | 'title'

export interface CareersListParams {
  search?: string
  department?: string
  location?: string
  work_format?: string
  employment_type?: string
  ordering?: CareersOrdering
  page?: number
  page_size?: number
}

export interface ApplyInput {
  submission_token: string
  full_name: string
  phone: string
  email: string
  city: string
  experience: string
  education: string
  skills: string
  cover_letter: string
  portfolio_url: string
  source: string
  consent: boolean
  website: string
  resume: File | null
}

export interface ApplyResult {
  number: string
  vacancy: { title: string; slug: string }
  message: string
}

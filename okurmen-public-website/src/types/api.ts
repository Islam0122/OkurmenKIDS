/**
 * Exactly what the Django public API returns:
 *   /api/v1/public/site/*      — apps.website.public
 *   /api/v1/public/news/*      — apps.academy_news.public
 *   /api/v1/public/projects/*  — apps.projects.public
 * Nothing here is invented on the frontend.
 */

export type Lang = 'ru' | 'ky' | 'en'

export interface ImageAsset {
  url: string
  thumb: string
  width: number | null
  height: number | null
  caption: string
}

export interface Paginated<T> {
  count: number
  page: number
  page_size: number
  num_pages: number
  results: T[]
}

export type Counts = Record<string, number>

// --- Site settings / homepage --------------------------------------------

export interface Cta {
  label: string
  url: string
}

export interface Branch {
  id: number
  name: string
  address: string
  phone: string
  working_hours: string
  map_url: string | null
  latitude: number | null
  longitude: number | null
}

export type SectionKey =
  | 'video'
  | 'stats'
  | 'courses'
  | 'projects'
  | 'achievements'
  | 'news'
  | 'events'
  | 'team'
  | 'testimonials'
  | 'cta'

export interface HomeSection {
  key: SectionKey
  title: string
}

export interface Banner {
  title: string
  text: string
  image: ImageAsset | null
  cta_label: string
  cta_url: string
}

export interface SiteSettings {
  hero: {
    title: string
    subtitle: string
    image: ImageAsset | null
    primary_cta: Cta
    secondary_cta: Cta
  }
  intro_video: string | null
  about: { story: string; mission: string; vision: string }
  contacts: {
    phone: string | null
    whatsapp: string | null
    telegram: string | null
    instagram: string | null
    email: string | null
    working_hours: string | null
  }
  branches: Branch[]
  stats: { value: string; label: string }[]
  sections: HomeSection[]
  banners: Banner[]
}

export interface HomeData extends SiteSettings {
  courses: CourseCard[]
  projects: ProjectCard[]
  news: NewsCard[]
  events: EventCard[]
  achievements: AchievementCard[]
  team: TeamMember[]
  testimonials: Testimonial[]
}

// --- Courses ----------------------------------------------------------------

export type CourseIcon = 'code' | 'python' | 'web' | 'game' | 'robot' | 'digital' | 'design'

export interface CourseCard {
  slug: string
  title: string
  tagline: string
  icon: CourseIcon
  cover: ImageAsset | null
  age_min: number | null
  age_max: number | null
  duration: string | null
  schedule: string | null
  lessons: number | null
  price: string | null
  is_featured: boolean
}

export interface CourseDetail extends CourseCard {
  body: string
  outcomes: string[]
  curriculum: { title: string; text: string }[]
  subjects: string[]
  project_category: string | null
  updated_at: string
  projects: ProjectCard[]
}

// --- Student projects (apps.projects.public) ----------------------------------

export type ProjectCategory = 'html-css' | 'javascript' | 'react' | 'python' | 'other'

export interface ProjectCard {
  key: string
  title: string
  short_description: string
  technologies: string[]
  categories: ProjectCategory[]
  date: string
  /** «First name + initial», or null when the family did not approve a public name. */
  student: string | null
  group: string | null
  cover_url: string | null
}

export interface ProjectDetail extends ProjectCard {
  description: string
  trainer: string | null
  demo_url: string | null
  images: { url: string; is_cover: boolean }[]
}

export interface ProjectsPage extends Paginated<ProjectCard> {
  counts: Counts
}

// --- News (apps.academy_news.public) -------------------------------------------

export type NewsCategory = 'events' | 'achievements' | 'competitions' | 'education' | 'announcements' | 'activities'

export interface NewsCard {
  slug: string
  title: string
  excerpt: string
  category: NewsCategory
  published_at: string
  cover: ImageAsset | null
  photo_count: number
}

export interface NewsArticle extends Omit<NewsCard, 'photo_count'> {
  body: string
  author: string | null
  photos: ImageAsset[]
  related: NewsCard[]
}

export interface NewsPage extends Paginated<NewsCard> {
  counts: Counts
  featured: NewsCard | null
}

// --- Events ---------------------------------------------------------------------

export type EventPhase = 'upcoming' | 'ongoing' | 'completed'
export type EventCategory =
  | 'open_day'
  | 'hackathon'
  | 'competition'
  | 'workshop'
  | 'presentation'
  | 'parent_meeting'
  | 'other'

export interface EventCard {
  slug: string
  title: string
  excerpt: string
  category: EventCategory
  starts_at: string
  ends_at: string | null
  location: string | null
  branch: string | null
  cover: ImageAsset | null
  phase: EventPhase
  registration_open: boolean
  is_featured: boolean
}

export interface EventDetail extends EventCard {
  body: string
  branch_address: string | null
  photos: ImageAsset[]
  registration: { enabled: boolean; open: boolean; deadline: string | null; spots_left: number | null }
  updated_at: string
  related: EventCard[]
}

export interface EventsPage extends Paginated<EventCard> {
  counts: Counts
}

// --- Achievements -----------------------------------------------------------------

export type AchievementCategory =
  | 'competition'
  | 'award'
  | 'certificate'
  | 'student'
  | 'milestone'
  | 'partnership'
  | 'recognition'

export interface AchievementCard {
  slug: string
  title: string
  excerpt: string
  category: AchievementCategory
  date: string
  cover: ImageAsset | null
  photo_count: number
  is_featured: boolean
}

export interface AchievementDetail extends AchievementCard {
  body: string
  photos: ImageAsset[]
  updated_at: string
  related: AchievementCard[]
}

export interface AchievementsPage extends Paginated<AchievementCard> {
  counts: Counts
}

// --- Team, testimonials ----------------------------------------------------------------

export interface TeamMember {
  id: number
  name: string
  position: string
  specialization: string | null
  bio: string
  experience_years: number | null
  photo: ImageAsset | null
}

export interface Testimonial {
  id: number
  author_name: string
  author_role: 'parent' | 'student' | 'graduate'
  course: string | null
  text: string
  language: Lang
  rating: number | null
  photo: ImageAsset | null
  video_embed: string | null
  kind: 'text' | 'photo' | 'video'
  is_featured: boolean
}

export interface TestimonialsPage extends Paginated<Testimonial> {
  counts: Counts
  average_rating: number | null
}

// --- Forms ------------------------------------------------------------------------------

export type ContactMethod = 'phone' | 'whatsapp' | 'telegram'

export interface LeadInput {
  parent_name: string
  phone: string
  child_age: number
  course?: string
  branch?: number | null
  contact_method: ContactMethod
  message?: string
  language?: Lang
  source?: string
  utm_source?: string
  utm_medium?: string
  utm_campaign?: string
  website?: string
}

export interface RegistrationInput {
  parent_name: string
  phone: string
  child_name?: string
  child_age?: number | null
  comment?: string
  website?: string
}

export interface SubmitResult {
  ok: boolean
  duplicate: boolean
}

// --- Preview ----------------------------------------------------------------------------

export type PreviewData =
  | { kind: 'course'; item: CourseDetail }
  | { kind: 'event'; item: EventDetail }
  | { kind: 'achievement'; item: AchievementDetail }
  | { kind: 'news'; item: NewsArticle }

import type { ProjectDetail, ProjectListItem, ProjectOptions, ProjectStats } from '@/types/projects'

export function buildProject(overrides: Partial<ProjectListItem> = {}): ProjectListItem {
  return {
    id: 1,
    title: 'Приложение погоды',
    short_description: 'Прогноз на неделю',
    project_date: '2026-11-02',
    status: 'published',
    rating: 5,
    technologies: ['React', 'TypeScript'],
    student: { id: 7, full_name: 'Алия Садыкова', status: 'active' },
    group: { id: 3, name: 'NEXT 1' },
    author: { id: 1, full_name: 'Айгуль Сатыбалдиева', image: null },
    cover_url: null,
    images_count: 0,
    can_edit: true,
    created_at: '2026-11-02T10:00:00Z',
    updated_at: '2026-11-02T10:00:00Z',
    ...overrides,
  }
}

export function buildProjectDetail(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    ...buildProject(),
    description: 'Полное описание',
    github_url: 'https://github.com/aliya/weather',
    demo_url: '',
    figma_url: '',
    trainer_comment: 'Отличная работа',
    images: [],
    course: { id: 1, name: 'NEXT' },
    ...overrides,
  }
}

export const STATS: ProjectStats = {
  total_projects: 4, active_students: 3, projects_this_month: 2, projects_previous_month: 1,
  month_change_percent: 100, groups_with_projects: 2, drafts: 1,
}

export function buildOptions(overrides: Partial<ProjectOptions> = {}): ProjectOptions {
  return {
    can_create: true,
    groups: [{ id: 3, name: 'NEXT 1' }],
    students: [{ id: 7, full_name: 'Алия Садыкова' }],
    selectable_students: [
      { id: 7, full_name: 'Алия Садыкова', status: 'active', group: { id: 3, name: 'NEXT 1' }, projects_count: 1 },
      { id: 8, full_name: 'Бекзат Ушаков', status: 'active', group: { id: 4, name: 'JUNIOR 2' }, projects_count: 0 },
    ],
    technologies: ['React'],
    max_images: 12,
    ...overrides,
  }
}

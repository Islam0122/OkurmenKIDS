import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

import { ProjectsPage } from './ProjectsPage'
import { buildOptions, buildProject, STATS } from './projectFixtures'

vi.mock('@/api/projects', () => ({
  projectsApi: { list: vi.fn(), stats: vi.fn(), options: vi.fn(), remove: vi.fn() },
}))

import { projectsApi } from '@/api/projects'

describe('ProjectsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(projectsApi.stats).mockResolvedValue(STATS)
    vi.mocked(projectsApi.options).mockResolvedValue(buildOptions())
  })

  it('shows the KPI cards and the projects the backend returned', async () => {
    vi.mocked(projectsApi.list).mockResolvedValue(paginated([buildProject()]))
    renderWithProviders(<ProjectsPage />, { route: '/trainer/projects' })

    expect(await screen.findByRole('link', { name: 'Приложение погоды' })).toHaveAttribute('href', '/trainer/projects/1')
    expect(within(screen.getByRole('article')).getByText('Алия Садыкова')).toBeInTheDocument()
    expect(screen.getByText('Всего проектов')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('+100%')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Добавить проект' })).toBeInTheDocument()
  })

  it('offers the first-project CTA to a trainer on an empty gallery', async () => {
    vi.mocked(projectsApi.list).mockResolvedValue(paginated([]))
    renderWithProviders(<ProjectsPage />, { route: '/trainer/projects' })
    expect(await screen.findByText('Проектов пока нет')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Добавить первый проект студента' })).toBeInTheDocument()
  })

  it('never offers creation to a role that cannot create (Team Lead)', async () => {
    vi.mocked(projectsApi.options).mockResolvedValue(buildOptions({ can_create: false }))
    vi.mocked(projectsApi.list).mockResolvedValue(paginated([buildProject({ can_edit: false })]))
    renderWithProviders(<ProjectsPage />, { route: '/trainer/projects' })
    await screen.findByRole('link', { name: 'Приложение погоды' })
    expect(screen.queryByRole('button', { name: 'Добавить проект' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Действия с проектом/ })).not.toBeInTheDocument()
  })

  it('passes URL filters to the API and shows a no-results state', async () => {
    vi.mocked(projectsApi.list).mockResolvedValue(paginated([]))
    renderWithProviders(<ProjectsPage />, { route: '/trainer/projects?group=3&technology=React' })
    expect(await screen.findByText('Ничего не найдено')).toBeInTheDocument()
    expect(projectsApi.list).toHaveBeenCalledWith(expect.objectContaining({ group: '3', technology: 'React', page: 1 }))
  })

  it('deletes a project after confirmation', async () => {
    const user = userEvent.setup()
    vi.mocked(projectsApi.list).mockResolvedValue(paginated([buildProject()]))
    vi.mocked(projectsApi.remove).mockResolvedValue(undefined)
    renderWithProviders(<ProjectsPage />, { route: '/trainer/projects' })

    await user.click(await screen.findByRole('button', { name: 'Действия с проектом «Приложение погоды»' }))
    await user.click(screen.getByRole('menuitem', { name: 'Удалить' }))
    const dialog = screen.getByRole('dialog', { name: 'Удалить проект?' })
    await user.click(within(dialog).getByRole('button', { name: 'Удалить' }))

    await waitFor(() => expect(projectsApi.remove).toHaveBeenCalledWith(1))
    expect(await screen.findByText('Проект «Приложение погоды» удалён')).toBeInTheDocument()
  })

  it('switches to the list view', async () => {
    const user = userEvent.setup()
    vi.mocked(projectsApi.list).mockResolvedValue(paginated([buildProject()]))
    renderWithProviders(<ProjectsPage />, { route: '/trainer/projects' })
    await screen.findByRole('link', { name: 'Приложение погоды' })
    await user.click(screen.getByRole('radio', { name: 'Список' }))
    expect(screen.getByRole('radio', { name: 'Список' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('listitem')).toBeInTheDocument()
  })
})

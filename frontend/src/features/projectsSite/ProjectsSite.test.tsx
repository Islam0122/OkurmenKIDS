import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError, type AxiosResponse } from 'axios'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PublicProject, PublicProjectPage, PublicProjectSummary } from '@/api/publicProjects'
import { renderWithProviders } from '@/test/testUtils'

import { ProjectDetailPage } from './ProjectDetailPage'
import { ProjectsGalleryPage } from './ProjectsGalleryPage'

vi.mock('@/api/publicProjects', async (original) => {
  const actual = await original<typeof import('@/api/publicProjects')>()
  return { ...actual, publicProjectsApi: { list: vi.fn(), detail: vi.fn() } }
})
// The public pages never use the authenticated client.
vi.mock('@/api/client', async (original) => {
  const actual = await original<typeof import('@/api/client')>()
  const fail = () => { throw new Error('the public gallery used the authenticated API client') }
  return { ...actual, apiClient: { get: fail, post: fail, put: fail, patch: fail, delete: fail } }
})
const mockUseAuth = vi.fn()
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => mockUseAuth() }))

import { publicProjectsApi } from '@/api/publicProjects'

const api = vi.mocked(publicProjectsApi)

function summary(over: Partial<PublicProjectSummary> = {}): PublicProjectSummary {
  return {
    key: 'abc123', title: 'Weather App', short_description: 'Погода на неделю', technologies: ['React', 'TypeScript', 'CSS', 'Vite'],
    categories: ['react', 'javascript', 'html-css'], date: '2026-11-02', student: 'Алия С.', group: 'NEXT 1', cover_url: '/media/projects/a.png',
    ...over,
  }
}

function page(results: PublicProjectSummary[], over: Partial<PublicProjectPage> = {}): PublicProjectPage {
  return {
    count: results.length, page: 1, page_size: 12, num_pages: 1, results,
    counts: { all: results.length, 'html-css': 1, javascript: 1, react: 1, python: 0, other: 0 }, ...over,
  }
}

function render(route = '/projects') {
  return renderWithProviders(
    <Routes>
      <Route path="/projects" element={<ProjectsGalleryPage />} />
      <Route path="/projects/:key" element={<ProjectDetailPage />} />
      <Route path="/login" element={<div>Login page</div>} />
    </Routes>,
    { route },
  )
}

describe('public Student Projects gallery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    mockUseAuth.mockReturnValue({ user: null, status: 'guest', logout: vi.fn() })
  })

  it('shows published projects to a guest without ever asking to log in', async () => {
    api.list.mockResolvedValue(page([summary()]))
    render()
    expect(screen.getByRole('heading', { name: 'Student Projects' })).toBeInTheDocument()
    const card = await screen.findByRole('link', { name: /Weather App — Алия С., NEXT 1/ })
    expect(card).toHaveAttribute('href', '/projects/abc123')
    expect(within(card).getByText('React')).toBeInTheDocument()
    expect(within(card).getByText('+1')).toBeInTheDocument()
    expect(within(card).getByText('View Project')).toBeInTheDocument()
    expect(within(card).getByText('2 November 2026')).toBeInTheDocument()
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/portal')
    expect(screen.getByRole('link', { name: 'Login' })).toHaveAttribute('href', '/login')
  })

  it('filters by technology and searches through the public API', async () => {
    api.list.mockResolvedValue(page([summary()]))
    render()
    await screen.findByText('Weather App')
    await userEvent.click(screen.getByRole('button', { name: /^Python/ }))
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ category: 'python', q: '' })))
    expect(screen.getByRole('button', { name: /^Python/ })).toHaveAttribute('aria-pressed', 'true')

    await userEvent.type(screen.getByLabelText('Search projects'), 'weather')
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ category: 'python', q: 'weather' })))
  })

  it('names a student without a published name neutrally', async () => {
    api.list.mockResolvedValue(page([summary({ student: null })]))
    render()
    expect(await screen.findByText('Okurmen Kids student')).toBeInTheDocument()
  })

  it('has empty, no-results and error states', async () => {
    api.list.mockResolvedValue(page([]))
    const view = render()
    expect(await screen.findByText('No projects yet')).toBeInTheDocument()
    view.unmount()

    render('/projects?q=zzz')
    expect(await screen.findByText('Nothing found')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reset filters' }))
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ q: '' })))
  })

  it('offers a retry when the gallery cannot load', async () => {
    api.list.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(page([summary()]))
    render()
    await userEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Weather App')).toBeInTheDocument()
  })

  it('loads more projects page by page', async () => {
    api.list
      .mockResolvedValueOnce(page([summary()], { count: 2, num_pages: 2 }))
      .mockResolvedValueOnce(page([summary({ key: 'def456', title: 'Snake' })], { page: 2, count: 2, num_pages: 2 }))
    render()
    await userEvent.click(await screen.findByRole('button', { name: 'Show more projects' }))
    expect(await screen.findByText('Snake')).toBeInTheDocument()
    expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
  })
})

describe('public project details', () => {
  const project: PublicProject = {
    ...summary(), description: 'Полное описание\nвторая строка', trainer: null, demo_url: 'https://weather.example.kg',
    images: [{ url: '/media/projects/a.png', is_cover: true }, { url: '/media/projects/b.png', is_cover: false }],
  }

  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    mockUseAuth.mockReturnValue({ user: null, status: 'guest', logout: vi.fn() })
  })

  it('shows the project, its screenshots and the demo link', async () => {
    api.detail.mockResolvedValue(project)
    render('/projects/abc123')
    expect(await screen.findByRole('heading', { name: 'Weather App' })).toBeInTheDocument()
    expect(api.detail).toHaveBeenCalledWith('abc123')
    expect(screen.getByText('Алия С.')).toBeInTheDocument()
    expect(screen.getByText('NEXT 1')).toBeInTheDocument()
    expect(screen.queryByText('Trainer')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open live demo' })).toHaveAttribute('href', 'https://weather.example.kg')
    expect(screen.getByRole('link', { name: 'Open live demo' })).toHaveAttribute('target', '_blank')
    expect(document.title).toBe('OkurmenKids Digital — Weather App')

    await userEvent.click(screen.getByRole('button', { name: 'Open screenshot 1' }))
    const viewer = screen.getByRole('dialog', { name: 'Screenshot 1 of 2' })
    await userEvent.click(within(viewer).getByRole('button', { name: /Next/ }))
    expect(screen.getByRole('dialog', { name: 'Screenshot 2 of 2' })).toBeInTheDocument()
  })

  it('shows the trainer only when the API publishes it', async () => {
    api.detail.mockResolvedValue({ ...project, trainer: 'Ислам Дуйшобаев' })
    render('/projects/abc123')
    expect(await screen.findByText('Ислам Дуйшобаев')).toBeInTheDocument()
  })

  it('says «not found» for a draft or unknown project', async () => {
    api.detail.mockRejectedValue(new AxiosError('nf', 'ERR', undefined, undefined, { status: 404, data: {} } as AxiosResponse))
    render('/projects/nope')
    expect(await screen.findByText('Project not found')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'All projects' }).every((link) => link.getAttribute('href') === '/projects')).toBe(true)
  })
})

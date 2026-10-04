import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { teachersApi } from '@/api/teachers'
import { buildTeacher, buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { UserRole } from '@/types/auth'

import { ProfilePage } from './ProfilePage'

const mockRole = vi.hoisted(() => ({ role: 'teacher' as UserRole }))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: mockRole.role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))

// Production shape: SPA on Vercel, API on Railway — different origins.
vi.mock('@/api/client', () => ({ API_BASE_URL: 'https://okurmen-api.up.railway.app/api/v1' }))
vi.mock('@/api/teachers', () => ({ teachersApi: { me: vi.fn() } }))

describe('ProfilePage photo', () => {
  beforeEach(() => {
    mockRole.role = 'teacher'
    vi.mocked(teachersApi.me).mockReset()
  })

  it('shows a Team Lead their account — they have no Trainer profile', async () => {
    mockRole.role = 'team_lead'
    renderWithProviders(<ProfilePage />)

    expect(await screen.findByText('Team Lead — руководитель тренеров')).toBeInTheDocument()
    expect(teachersApi.me).not.toHaveBeenCalled()
  })

  it('loads a root-relative photo from the API origin', async () => {
    // GET /trainers/me/ serializes without the request, so Django sends a
    // root-relative URL; the SPA's own domain would answer with index.html.
    vi.mocked(teachersApi.me).mockResolvedValue(buildTeacher({ image: '/media/teachers/avatar.png' }))

    renderWithProviders(<ProfilePage />)

    const photo = await screen.findByRole('img')
    expect(photo).toHaveAttribute('src', 'https://okurmen-api.up.railway.app/media/teachers/avatar.png')
  })

  it('keeps an absolute photo URL as is', async () => {
    const absolute = 'https://okurmen-api.up.railway.app/media/teachers/avatar.png'
    vi.mocked(teachersApi.me).mockResolvedValue(buildTeacher({ image: absolute }))

    renderWithProviders(<ProfilePage />)

    expect(await screen.findByRole('img')).toHaveAttribute('src', absolute)
  })

  it('shows the placeholder when there is no photo', async () => {
    vi.mocked(teachersApi.me).mockResolvedValue(buildTeacher({ image: null }))

    renderWithProviders(<ProfilePage />)

    expect(await screen.findByText('Профиль')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})

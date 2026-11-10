import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'

import { parseMarkup } from './markup'

vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))

import { apiClient } from '@/api/client'
import type { SiteMeta } from './api'
import { ResourcePage } from './ResourcePage'

const meta = (overrides: Partial<SiteMeta['permissions']> = {}): SiteMeta => ({
  permissions: { can_edit: true, can_approve: false, require_approval: false, can_delete_leads: false, ...overrides },
  public_site_url: 'https://kids.example.kg',
  choices: {
    workflow: [{ value: 'draft', label: 'Черновик' }, { value: 'published', label: 'Опубликовано' }],
    achievement_category: [{ value: 'award', label: 'Награда' }, { value: 'competition', label: 'Победа в соревновании' }],
  },
  lms: { courses: [], teachers: [], projects: [], news: [] },
})

const row = { id: 7, title: 'Олимпиада', category: 'award', date: '2026-10-01', workflow_state: 'draft', cover: null, photos: [], preview: { url: 'https://kids.example.kg/preview/abc' } }

describe('CMS публичного сайта', () => {
  let metaData = meta()
  beforeEach(() => {
    metaData = meta()
    vi.mocked(apiClient.get).mockReset().mockImplementation(async (url: string) => ({
      data: url.endsWith('/meta/') ? metaData : url.endsWith('/achievements/') ? { count: 1, next: null, previous: null, results: [row] } : [],
    }))
    vi.mocked(apiClient.patch).mockReset().mockResolvedValue({ data: row })
    vi.mocked(apiClient.post).mockReset().mockResolvedValue({ data: { ...row, workflow_state: 'published' } })
  })

  it('список, редактор, предпросмотр и публикация', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ResourcePage resource="achievements" />)
    await user.click(await screen.findByText('Олимпиада'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('link', { name: /Предпросмотр/ })).toHaveAttribute('href', 'https://kids.example.kg/preview/abc')
    await user.clear(within(dialog).getByLabelText('Название *'))
    await user.type(within(dialog).getByLabelText('Название *'), 'Олимпиада 2026')
    await user.click(within(dialog).getByRole('button', { name: 'Опубликовать' }))
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/marketing/site/achievements/7/publish/', expect.objectContaining({ keep_schedule: false })))
    expect(apiClient.patch).toHaveBeenCalledWith('/marketing/site/achievements/7/', expect.objectContaining({ title: 'Олимпиада 2026', category: 'award' }))
  })

  it('без права публикации — только «На согласование»', async () => {
    metaData = meta({ require_approval: true })
    const user = userEvent.setup()
    renderWithProviders(<ResourcePage resource="achievements" />)
    await user.click(await screen.findByText('Олимпиада'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByRole('button', { name: 'Опубликовать' })).not.toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'На согласование' }))
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/marketing/site/achievements/7/submit_review/', {}))
  })

  it('разметка редактора совпадает с сайтом', () => {
    expect(parseMarkup('## Итоги\n- один\n> цитата\nhttps://youtu.be/dQw4w9WgXcQ').map((b) => b.type)).toEqual(['heading', 'list', 'quote', 'video'])
  })
})

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError, AxiosHeaders } from 'axios'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '@/components/ui/Toast'
import { createTestQueryClient } from '@/test/testUtils'

vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))

import { apiClient } from '@/api/client'
import { DashboardPage } from './DashboardPage'
import { CmsFormatError } from './errors'
import { parseOverview } from './overview'

const counts = (published = 0, draft = 0) => ({ draft, review: 0, scheduled: 0, published, archived: 0 })
const row = { resource: 'news', type_label: 'Новость', id: 3, title: 'Набор открыт', state: 'draft', cover: null, updated_at: '2026-11-10T10:00:00Z', published_at: '2026-11-10T10:00:00Z', issues: ['seo'] }

/** The current server (apps.website.cms.OverviewView). */
const current = {
  courses: counts(1), events: counts(2, 1), achievements: counts(), news: counts(4, 1), team: counts(), testimonials: counts(),
  leads_new: 5, leads_by_status: { new: 5 }, registrations_new: 1, upcoming_events: 2, media: 9, projects: 7, featured_projects: 3,
  recent: [row], recently_published: [], drafts: [row], attention: [row], coverage: { news: { total: 5, ky: 1, en: 0, seo: 2 } },
}
/** The earlier server (before the CMS update is deployed): counters only — the production crash. */
const legacy = {
  courses: { draft: 0, review: 0, scheduled: 0, published: 1 }, events: { draft: 1, review: 0, scheduled: 0, published: 2 },
  achievements: { draft: 0, review: 0, scheduled: 0, published: 0 }, team: { draft: 0, review: 0, scheduled: 0, published: 0 },
  testimonials: { draft: 0, review: 0, scheduled: 0, published: 0 }, news: { draft: 1, scheduled: 0, published: 4 },
  leads_new: 5, registrations_new: 1, upcoming_events: 2, media: 9,
}
const meta = { permissions: { can_edit: true, can_approve: true, require_approval: false, can_delete_leads: false }, public_site_url: 'https://kids.example.kg', choices: {} }

function respond(overview: () => Promise<unknown>) {
  vi.mocked(apiClient.get).mockReset().mockImplementation(async (url: string) => {
    if (url.endsWith('/meta/')) return { data: meta }
    if (url.endsWith('/overview/')) return { data: await overview() }
    return { data: [] }
  })
}

function renderDashboard() {
  const router = createMemoryRouter([{ path: '/marketing/site', element: <DashboardPage /> }, { path: '*', element: null }], { initialEntries: ['/marketing/site'] })
  render(<QueryClientProvider client={createTestQueryClient()}><ToastProvider><RouterProvider router={router} /></ToastProvider></QueryClientProvider>)
}

describe('parseOverview — граница API', () => {
  it('текущий ответ сервера проходит без изменений', () => {
    const o = parseOverview(current)
    expect(o.drafts).toEqual([row])
    expect(o.projects).toBe(7)
    expect(o.coverage?.news.total).toBe(5)
  })

  it('старый ответ (только счётчики): списков нет — null, а не выдуманные строки или нули', () => {
    const o = parseOverview(legacy)
    expect(o.drafts).toBeNull()
    expect(o.recent).toBeNull()
    expect(o.attention).toBeNull()
    expect(o.coverage).toBeNull()
    expect(o.projects).toBeNull()
    expect(o.news).toEqual(counts(4, 1)) // news has no «review» / «archived» states — truly 0
  })

  it('пустые массивы остаются пустыми, битые строки отбрасываются', () => {
    const o = parseOverview({ ...current, drafts: [], recent: [row, null, { id: 'x' }], attention: [{ ...row, issues: null }] })
    expect(o.drafts).toEqual([])
    expect(o.recent).toEqual([row])
    expect(o.attention?.[0].issues).toEqual([])
  })

  it('null, массив или HTML вместо объекта — ошибка формата', () => {
    for (const bad of [null, undefined, [], '<!doctype html>']) expect(() => parseOverview(bad)).toThrow(CmsFormatError)
  })
})

describe('Обзор сайта — состояния', () => {
  beforeEach(() => vi.spyOn(console, 'error').mockImplementation(() => {}))

  it('правильные данные', async () => {
    respond(async () => current)
    renderDashboard()
    expect(await screen.findByText('Новые заявки')).toBeInTheDocument()
    expect(screen.getAllByText('Набор открыт').length).toBeGreaterThan(0)
    expect(screen.getAllByText('7').length).toBeGreaterThan(0)
  })

  it('пустые массивы — подсказки пустого состояния', async () => {
    respond(async () => ({ ...current, recent: [], drafts: [], recently_published: [], attention: [] }))
    renderDashboard()
    expect(await screen.findByText(/Изменений пока нет/)).toBeInTheDocument()
    expect(screen.getByText('Черновиков нет — всё опубликовано.')).toBeInTheDocument()
    expect(screen.getByText('Всё заполнено. Отличная работа!')).toBeInTheDocument()
  })

  it('старый сервер (причина ошибки в production): страница не падает, списки помечены недоступными', async () => {
    const user = userEvent.setup()
    respond(async () => legacy)
    renderDashboard()
    expect(await screen.findByText('Новые заявки')).toBeInTheDocument()
    expect(screen.getAllByText(/Сервер пока не передаёт этот список/)).toHaveLength(4)
    expect(screen.getByText('—')).toBeInTheDocument() // projects: unknown, not «0»
    await user.click(screen.getByRole('button', { name: 'Предпросмотр' }))
    expect(screen.getAllByText(/Сервер пока не передаёт этот список/)).toHaveLength(5)
  })

  it('ответ null — понятная ошибка с повтором', async () => {
    respond(async () => null)
    renderDashboard()
    expect((await screen.findAllByText(/неожиданном формате/)).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /Повторить/ }).length).toBeGreaterThan(0)
  })

  it('сервер недоступен, затем снова отвечает — повтор загружает данные', async () => {
    const user = userEvent.setup()
    let down = true
    respond(async () => { if (down) throw Object.assign(new Error('Network Error'), { isAxiosError: true }); return current })
    renderDashboard()
    const retry = await screen.findAllByRole('button', { name: /Повторить/ })
    down = false
    await user.click(retry[0])
    await waitFor(() => expect(screen.getAllByText('Набор открыт').length).toBeGreaterThan(0))
  })

  it('нет прав (403) — ошибка вместо падения', async () => {
    const config = { headers: new AxiosHeaders() }
    respond(async () => {
      throw new AxiosError('Forbidden', 'ERR_BAD_REQUEST', config, null, {
        status: 403, statusText: 'Forbidden', headers: {}, config, data: { detail: 'Управление сайтом доступно маркетингу, директору и администратору.' },
      })
    })
    renderDashboard()
    expect((await screen.findAllByText(/доступно маркетингу/)).length).toBeGreaterThan(0)
  })
})

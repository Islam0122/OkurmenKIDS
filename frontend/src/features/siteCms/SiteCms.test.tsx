import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '@/components/ui/Toast'
import { createTestQueryClient } from '@/test/testUtils'

import { buildBody, initialValues, langFill, mergeSaved } from './editorState'
import { parseMarkup } from './markup'
import { RESOURCES } from './schema'

vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))

import { apiClient } from '@/api/client'
import type { SiteMeta } from './api'
import { ContentEditorRoute } from './ContentEditorPage'
import { ContentListRoute } from './ContentListPage'
import { navFor } from './nav'

const meta = (overrides: Partial<SiteMeta['permissions']> = {}): SiteMeta => ({
  permissions: { can_edit: true, can_approve: false, require_approval: false, can_delete_leads: false, ...overrides },
  public_site_url: 'https://kids.example.kg',
  user_id: 1,
  staff: [{ id: 1, name: 'Айжан', role: 'marketing' }],
  choices: {
    workflow: [{ value: 'draft', label: 'Черновик' }, { value: 'published', label: 'Опубликовано' }],
    achievement_category: [{ value: 'award', label: 'Награда' }, { value: 'competition', label: 'Победа в соревновании' }],
  },
  lms: { courses: [], teachers: [], projects: [], news: [] },
})

const row = {
  id: 7, title: 'Олимпиада', title_ky: '', title_en: '', category: 'award', date: '2026-10-01', workflow_state: 'draft', status: 'draft',
  cover: null, photos: [], preview: { url: 'https://kids.example.kg/preview/abc' }, updated_at: '2026-11-01T10:00:00Z', seo_title: '', seo_description: '',
}

function renderAt(path: string, routes: { path: string; element: ReactElement }[]) {
  const router = createMemoryRouter([...routes, { path: '*', element: <p>другая страница</p> }], { initialEntries: [path] })
  render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ToastProvider><RouterProvider router={router} /></ToastProvider>
    </QueryClientProvider>,
  )
  return router
}

const editorRoutes = [
  { path: '/marketing/site/:resource/:id', element: <ContentEditorRoute /> },
  { path: '/marketing/site/:resource', element: <ContentListRoute /> },
]

describe('Управление сайтом — редактор', () => {
  let metaData = meta()
  beforeEach(() => {
    metaData = meta()
    window.localStorage.clear()
    vi.mocked(apiClient.get).mockReset().mockImplementation(async (url: string) => ({
      data: url.endsWith('/meta/') ? metaData
        : url.endsWith('/achievements/7/') ? row
          : url.endsWith('/achievements/') ? { count: 1, next: null, previous: null, results: [row] } : [],
    }))
    vi.mocked(apiClient.patch).mockReset().mockImplementation(async (_url: string, body: unknown) => ({ data: { ...row, ...(body as object) } }))
    vi.mocked(apiClient.post).mockReset().mockResolvedValue({ data: { ...row, workflow_state: 'published', status: 'published' } })
  })

  it('языки не теряются при переключении, публикация сохраняет все три версии', async () => {
    const user = userEvent.setup()
    renderAt('/marketing/site/achievements/7', editorRoutes)
    const title = await screen.findByLabelText(/^Название/)
    await user.clear(title)
    await user.type(title, 'Олимпиада 2026')
    await user.click(screen.getByRole('tab', { name: /KG/ }))
    await user.type(screen.getByLabelText(/Название \(KG\)/), 'Олимпиада KG')
    await user.click(screen.getByRole('tab', { name: /EN/ }))
    await user.type(screen.getByLabelText(/Название \(EN\)/), 'Olympiad')
    await user.click(screen.getByRole('tab', { name: /RU/ }))
    expect(screen.getByLabelText(/^Название/)).toHaveValue('Олимпиада 2026')
    await user.click(screen.getAllByRole('button', { name: 'Опубликовать' })[0])
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/marketing/site/achievements/7/publish/', expect.objectContaining({ keep_schedule: false })))
    expect(apiClient.patch).toHaveBeenCalledWith('/marketing/site/achievements/7/', expect.objectContaining({
      title: 'Олимпиада 2026', title_ky: 'Олимпиада KG', title_en: 'Olympiad', category: 'award',
    }))
  })

  it('«Формат занятий» курса: отдельное многострочное поле на каждом языке, без лимита 120, переносы сохраняются', async () => {
    const course = {
      id: 9, title: 'Python', title_ky: '', title_en: '', tagline: '', tagline_ky: '', tagline_en: '', icon: 'code', status: 'draft', workflow_state: 'draft',
      schedule: '2 раза в неделю', schedule_ky: '', schedule_en: '', cover: null, preview: null, updated_at: '2026-11-01T10:00:00Z', seo_title: '', seo_description: '',
    }
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => ({ data: url.endsWith('/meta/') ? metaData : url.endsWith('/courses/9/') ? course : [] }))
    vi.mocked(apiClient.patch).mockImplementation(async (_url: string, body: unknown) => ({ data: { ...course, ...(body as object) } }))
    const ru = 'Пн, Ср, Пт — 18:00–19:30\nГруппы до 10 детей\n' + 'Подробнее о формате: '.repeat(6)
    const ky = 'Дш, Шр, Жм — 18:00–19:30\nТопто 10 баладан ашпайт'
    const en = 'Mon, Wed, Fri — 6:00–7:30 pm\nGroups of up to 10 children'
    const user = userEvent.setup()
    renderAt('/marketing/site/courses/9', editorRoutes)

    const field = await screen.findByLabelText(/^Формат занятий$/)
    expect(field.tagName).toBe('TEXTAREA')
    expect(field).not.toHaveAttribute('maxLength')
    expect(field).toHaveValue('2 раза в неделю')
    await user.clear(field)
    await user.click(field)
    await user.paste(ru)
    expect(ru.length).toBeGreaterThan(120)

    await user.click(screen.getByRole('tab', { name: /KG/ }))
    const kyField = screen.getByLabelText(/Формат занятий \(KG\)/)
    expect(kyField.tagName).toBe('TEXTAREA')
    expect(kyField).toHaveValue('')
    await user.click(kyField)
    await user.paste(ky)
    await user.click(screen.getByRole('tab', { name: /EN/ }))
    await user.click(screen.getByLabelText(/Формат занятий \(EN\)/))
    await user.paste(en)
    await user.click(screen.getByRole('tab', { name: /RU/ }))
    expect(screen.getByLabelText(/^Формат занятий$/)).toHaveValue(ru)

    await user.click(screen.getAllByRole('button', { name: /Сохранить/ })[0])
    await waitFor(() => expect(apiClient.patch).toHaveBeenCalledWith('/marketing/site/courses/9/', expect.objectContaining({
      schedule: ru, schedule_ky: ky, schedule_en: en,
    })))
  })

  it('без права публикации — «На согласование»', async () => {
    metaData = meta({ require_approval: true })
    const user = userEvent.setup()
    renderAt('/marketing/site/achievements/7', editorRoutes)
    await screen.findByLabelText(/^Название/)
    expect(screen.queryByRole('button', { name: 'Опубликовать' })).not.toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'На согласование' })[0])
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/marketing/site/achievements/7/submit_review/', {}))
  })

  it('удаление — только после подтверждения', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.delete).mockReset().mockResolvedValue({})
    renderAt('/marketing/site/achievements/7', editorRoutes)
    await screen.findByLabelText(/^Название/)
    await user.click(screen.getAllByRole('button', { name: 'Ещё действия' })[0])
    await user.click(screen.getByRole('menuitem', { name: /Удалить/ }))
    expect(apiClient.delete).not.toHaveBeenCalled()
    await user.click(within(screen.getByRole('dialog', { name: 'Удалить материал?' })).getByRole('button', { name: 'Удалить' }))
    await waitFor(() => expect(apiClient.delete).toHaveBeenCalledWith('/marketing/site/achievements/7/'))
  })

  it('уход с несохранёнными изменениями спрашивает подтверждение', async () => {
    const user = userEvent.setup()
    const router = renderAt('/marketing/site/achievements/7', editorRoutes)
    await user.type(await screen.findByLabelText(/^Название/), ' X')
    await router.navigate('/elsewhere')
    expect(await screen.findByRole('dialog', { name: 'Уйти без сохранения?' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/marketing/site/achievements/7')
  })

  it('список: статус и языки', async () => {
    renderAt('/marketing/site/achievements', editorRoutes)
    expect((await screen.findAllByText('Олимпиада')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Черновик').length).toBeGreaterThan(0)
    expect(screen.getAllByText('KG').length).toBeGreaterThan(0)
  })
})

describe('логика редактора', () => {
  const def = RESOURCES.achievements

  it('изображение из медиатеки уходит ссылкой media:<id>, неизменённое — не отправляется', () => {
    const values = initialValues(def, row as never)
    expect(buildBody(def, values)).not.toHaveProperty('cover')
    expect(buildBody(def, { ...values, cover: { ref: 'media:5', preview: '/m/5.jpg' } }).cover).toBe('media:5')
  })

  it('полнота переводов и слияние после автосохранения', () => {
    const values = { ...initialValues(def, row as never), title_ky: 'KG' }
    expect(langFill(def, values).ky).toBe('full')
    expect(langFill(def, values).en).toBe('empty')
    // a field edited during the save keeps the newer text
    expect(mergeSaved({ title: 'новее', slug: '' }, { title: 'старое', slug: '' }, { title: 'старое', slug: 'olimpiada' })).toEqual({ title: 'новее', slug: 'olimpiada' })
  })

  it('отдел продаж видит только заявки', () => {
    const items = navFor(false).flatMap((g) => g.items.map((i) => i.to))
    expect(items).toEqual(['/marketing/site/leads', '/marketing/site/leads/board'])
    expect(navFor(true).map((g) => g.label)).toEqual(['', 'Контент', 'Медиа', 'Обратная связь', 'Настройки'])
  })

  it('разметка редактора совпадает с сайтом', () => {
    expect(parseMarkup('## Итоги\n- один\n> цитата\nhttps://youtu.be/dQw4w9WgXcQ').map((b) => b.type)).toEqual(['heading', 'list', 'quote', 'video'])
  })
})

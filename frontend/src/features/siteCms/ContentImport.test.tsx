import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))

import { apiClient } from '@/api/client'
import { ContentImportPage } from './ContentImportPage'
import type { Batch, ImportRow } from './importApi'

const row = (over: Partial<ImportRow>): ImportRow => ({
  key: 'events:2', kind: 'events', row: 2, title: 'Хакатон', category: 'hackathon', category_raw: 'hackathon', date: '2027-03-14T10:00:00+06:00',
  languages: { ru: true, ky: true, en: false }, status: 'draft', status_raw: '', cover: '', verification_note: '',
  errors: [], warnings: [], duplicate: null, valid: true, ...over,
})

const batch: Batch = {
  id: 5, file_name: 'content.xlsx', file_size: 2048, created_by_name: 'Админ', content_type: 'mixed', content_type_label: 'Несколько типов',
  status: 'preview', status_label: 'Проверка', total_rows: 3, selected_rows: 0, imported_count: 0, created_count: 0, updated_count: 0,
  skipped_count: 0, failed_count: 0, error_rows: 1, created_at: '2026-11-11T10:00:00Z', finished_at: null,
  sheets: { events: 2, news: 1 },
  rows: [
    row({}),
    row({ key: 'events:3', row: 3, title: '', valid: false, errors: [{ field: 'title_ru', message: 'Нет названия на русском (обязательное поле).' }] }),
    row({ key: 'news:2', kind: 'news', title: 'Набор открыт', category: 'announcements',
      duplicate: { id: 9, title: 'Набор открыт', slug: 'nabor', status: 'draft', status_label: 'Черновик', updatable: true } }),
  ],
  results: {},
}

describe('Массовое заполнение контента', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset().mockImplementation(async (url: string) => ({
      data: url.endsWith('/meta/') ? { permissions: { can_edit: true, can_approve: true, require_approval: false, can_delete_leads: true, can_import: true }, choices: {}, public_site_url: null } : {},
    }))
    vi.mocked(apiClient.post).mockReset().mockImplementation(async (url: string, body?: unknown) => {
      if (url.endsWith('/preview/')) return { data: batch }
      const b = body as { rows: string[] }
      return {
        data: {
          ...batch, status: 'completed', finished_at: '2026-11-11T10:01:00Z', created_count: 1, updated_count: 1,
          results: Object.fromEntries(b.rows.map((k) => [k, { result: k.startsWith('news') ? 'updated' : 'created', message: 'ok', object_id: 1, kind: k.split(':')[0], row: 2, title: k, verification_note: '' }])),
        },
      }
    })
  })

  it('загрузка → просмотр → проверка → импорт с подтверждением обновления', async () => {
    const user = userEvent.setup()
    const { container } = renderWithProviders(<ContentImportPage />)
    const input = await waitFor(() => {
      const el = container.querySelector<HTMLInputElement>('input[type=file]')
      if (!el) throw new Error('no input')
      return el
    })
    await user.upload(input, new File(['x'], 'content.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))
    expect(screen.getByText('content.xlsx')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Проверить файл' }))

    // Preview: the invalid row cannot be selected, valid ones are selected
    expect(await screen.findByRole('checkbox', { name: 'Строка 3' })).toBeDisabled()
    expect(screen.getAllByRole('checkbox', { name: 'Строка 2' }).every((c) => (c as HTMLInputElement).checked)).toBe(true)
    await user.click(screen.getByRole('button', { name: /Проверка выбранных \(2\)/ }))

    // Validation: duplicate → choose update
    expect(screen.getByText('Ошибки — эти строки не будут импортированы')).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: 'Обновить' }))
    await user.click(screen.getByRole('button', { name: 'Перейти к импорту' }))

    // Import needs explicit confirmation of the update
    const go = screen.getByRole('button', { name: 'Импортировать 2' })
    expect(go).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: /подтверждаю обновление 1/ }))
    await user.click(go)
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/marketing/site/import/5/commit/', {
      rows: ['events:2', 'news:2'], update: ['news:2'], confirm_update: true, finalize: true,
    }))
    const results = await screen.findByText('Результат по строкам')
    expect(within(results.closest('.card') as HTMLElement).getByText('Обновлено')).toBeInTheDocument()
  })

  it('без права импорта — сообщение', async () => {
    vi.mocked(apiClient.get).mockImplementation(async () => ({ data: { permissions: { can_edit: true, can_import: false }, choices: {} } }))
    renderWithProviders(<ContentImportPage />)
    expect(await screen.findByText('Нет доступа')).toBeInTheDocument()
  })
})

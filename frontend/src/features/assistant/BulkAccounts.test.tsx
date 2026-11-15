import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { BulkPreview, BulkRun, Options } from '@/types/assistant'

vi.mock('@/api/assistant', () => ({
  assistantApi: {
    options: vi.fn(),
    bulkPreview: vi.fn(),
    bulkRuns: vi.fn(),
    bulkRun: vi.fn(),
    bulkCreate: vi.fn(),
    bulkProcess: vi.fn(),
    bulkRetry: vi.fn(),
    bulkExport: vi.fn(),
  },
  surveysApi: {},
}))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 1, first_name: 'Asel', last_name: 'K', role: 'assistant', username: 'a', email: 'a@a', is_active: true, is_verified: true }, logout: vi.fn() }),
}))

import { assistantApi } from '@/api/assistant'

import { AssistantBulkAccountsPage } from './pages/BulkAccountsPage'

const OPTIONS = {
  groups: [
    { id: 1, name: 'PRO-01', course: 'Python', status: 'active', students_count: 2, max_students: null },
    { id: 2, name: 'PRO-02', course: 'Python', status: 'active', students_count: 2, max_students: null },
  ],
} as unknown as Options

const PREVIEW: BulkPreview = {
  scope: 'all',
  group_ids: [],
  group_names: [],
  total: 4,
  existing: 1,
  to_create: 3,
  students: [
    { id: 1, full_name: 'Бегалы Асанов', group: 'PRO-01', has_account: false, login: 'begaly01' },
    { id: 2, full_name: 'Талант Касымов', group: 'PRO-02', has_account: true, login: 'talant01' },
  ],
}

function run(overrides: Partial<BulkRun> = {}): BulkRun {
  return {
    id: 9,
    scope: 'all',
    scope_label: 'все активные студенты',
    group_names: [],
    status: 'completed',
    status_display: 'Завершён',
    created_at: '2026-11-15T10:00:00Z',
    finished_at: '2026-11-15T10:01:00Z',
    created_by: 'Asel K',
    retry_of: null,
    counts: { total: 4, existing: 1, created: 2, failed: 1, pending: 0 },
    progress: 100,
    export: { state: 'ready', label: 'Готов к выгрузке', downloadable: true, expires_at: '2026-11-16T10:00:00Z', exported_at: null },
    failed: [{ id: 5, student_id: 4, full_name: 'Bilal Omurov', group: 'PRO-02', reason: 'Тестовая ошибка' }],
    created: [
      { student_id: 1, full_name: 'Бегалы Асанов', group: 'PRO-01', login: 'begaly01' },
      { student_id: 3, full_name: 'Бегалы Жумабеков', group: 'PRO-01', login: 'begaly02' },
    ],
    ...overrides,
  }
}

describe('Кабинеты учеников (пакетное создание)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(assistantApi.options).mockResolvedValue(OPTIONS)
    vi.mocked(assistantApi.bulkPreview).mockResolvedValue(PREVIEW)
    vi.mocked(assistantApi.bulkRuns).mockResolvedValue({ results: [] })
  })

  it('shows the preview before anything is created', async () => {
    renderWithProviders(<AssistantBulkAccountsPage />, { route: '/assistant/students/accounts' })
    expect(await screen.findByText('begaly01')).toBeInTheDocument()
    expect(screen.getByText('Уже есть: talant01')).toBeInTheDocument()
    expect(assistantApi.bulkCreate).not.toHaveBeenCalled()
  })

  it('asks for confirmation, then runs the batch step by step and offers the one-time download', async () => {
    const user = userEvent.setup()
    const first = run({ status: 'running', progress: 0, counts: { total: 4, existing: 1, created: 0, failed: 0, pending: 3 }, export: { state: 'none', label: 'Нет учётных данных', downloadable: false, expires_at: null, exported_at: null }, failed: [], created: [] })
    const second = run({ status: 'completed', counts: { total: 4, existing: 1, created: 2, failed: 1, pending: 0 } })
    vi.mocked(assistantApi.bulkCreate).mockResolvedValue(first)
    vi.mocked(assistantApi.bulkRun).mockResolvedValue(second)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    vi.mocked(assistantApi.bulkProcess).mockResolvedValueOnce({ ...first, counts: { ...first.counts, pending: 1, created: 2, failed: 1 }, progress: 75 }).mockResolvedValueOnce(second)
    vi.mocked(assistantApi.bulkExport).mockResolvedValue(new Blob(['xlsx'], { type: 'application/octet-stream' }))
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:x')
    globalThis.URL.revokeObjectURL = vi.fn()

    renderWithProviders(<AssistantBulkAccountsPage />, { route: '/assistant/students/accounts' })
    await user.click(await screen.findByRole('button', { name: 'Создать аккаунты (3)' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/Временные пароли будут доступны только в Excel/)).toBeInTheDocument()
    expect(assistantApi.bulkCreate).not.toHaveBeenCalled()

    await user.click(within(dialog).getByRole('button', { name: 'Создать' }))
    await waitFor(() => expect(assistantApi.bulkCreate).toHaveBeenCalledWith('all', []))
    await waitFor(() => expect(assistantApi.bulkProcess).toHaveBeenCalledTimes(2))
    expect(assistantApi.bulkProcess).toHaveBeenCalledWith(9, 10)

    await screen.findByRole('button', { name: 'Скачать Excel' })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Скачать Excel' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Скачать Excel' }))
    await waitFor(() => expect(assistantApi.bulkExport).toHaveBeenCalledWith(9))
    expect(screen.getByText('Ошибки')).toBeInTheDocument()
    expect(screen.getByText('Тестовая ошибка')).toBeInTheDocument()
  })

  it('retries only failed students through a new run', async () => {
    const user = userEvent.setup()
    const original = run()
    vi.mocked(assistantApi.bulkRuns).mockResolvedValue({ results: [original] })
    vi.mocked(assistantApi.bulkRun).mockResolvedValue(original)
    const retryRun = run({ id: 10, retry_of: 9, counts: { total: 1, existing: 0, created: 0, failed: 0, pending: 1 }, status: 'pending', failed: [], created: [] })
    vi.mocked(assistantApi.bulkRetry).mockResolvedValue(retryRun)
    vi.mocked(assistantApi.bulkProcess).mockResolvedValue(run({ id: 10, retry_of: 9, counts: { total: 1, existing: 0, created: 1, failed: 0, pending: 0 }, failed: [], created: [] }))

    renderWithProviders(<AssistantBulkAccountsPage />, { route: '/assistant/students/accounts' })
    await user.click(await screen.findByRole('button', { name: 'Повторить неудачные' }))
    await waitFor(() => expect(assistantApi.bulkRetry).toHaveBeenCalledWith(9))
    await waitFor(() => expect(assistantApi.bulkProcess).toHaveBeenCalledWith(10, 10))
  })

  it('needs a group before the groups scope can be previewed', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AssistantBulkAccountsPage />, { route: '/assistant/students/accounts' })
    await user.click(await screen.findByRole('button', { name: /Выбранные группы/ }))
    expect(screen.getByText('Выберите группы')).toBeInTheDocument()
    expect(assistantApi.bulkPreview).not.toHaveBeenCalledWith('groups', [1])
    await user.click(screen.getByRole('button', { name: /PRO-01/ }))
    await waitFor(() => expect(assistantApi.bulkPreview).toHaveBeenCalledWith('groups', [1]))
  })

  it('does not offer a download when the file is already used', async () => {
    vi.mocked(assistantApi.bulkRuns).mockResolvedValue({ results: [run({ export: { state: 'downloaded', label: 'Выгружен', downloadable: false, expires_at: null, exported_at: '2026-11-15T10:05:00Z' } })] })
    vi.mocked(assistantApi.bulkRun).mockResolvedValue(run({ export: { state: 'downloaded', label: 'Выгружен', downloadable: false, expires_at: null, exported_at: '2026-11-15T10:05:00Z' } }))
    renderWithProviders(<AssistantBulkAccountsPage />, { route: '/assistant/students/accounts' })
    expect(await screen.findByRole('button', { name: 'Скачать Excel' })).toBeDisabled()
  })
})

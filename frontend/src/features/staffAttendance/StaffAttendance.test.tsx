import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError } from 'axios'
import type { AxiosResponse } from 'axios'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { AdminMeta, DayRow, MarkResult, MyStatus, Overview, WorkSession } from '@/types/staffAttendance'

vi.mock('@/api/staffAttendance', () => ({
  staffAttendanceApi: {
    myStatus: vi.fn(), verifyOffice: vi.fn(), checkIn: vi.fn(), checkOut: vi.fn(), myHistory: vi.fn(), myStats: vi.fn(),
    meta: vi.fn(), overview: vi.fn(), records: vi.fn(), exportCsv: vi.fn(), employee: vi.fn(), adjust: vi.fn(),
    createManual: vi.fn(), locations: vi.fn(), createLocation: vi.fn(), updateLocation: vi.fn(), locationQrSvg: vi.fn(),
    settings: vi.fn(), updateSettings: vi.fn(), schedules: vi.fn(), saveSchedule: vi.fn(), deleteSchedule: vi.fn(),
  },
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 7, role: 'teacher', first_name: 'Айбек', last_name: 'Тренер' }, status: 'authenticated', logout: vi.fn() }),
}))

import { staffAttendanceApi } from '@/api/staffAttendance'

import { AdminAttendancePage } from './AdminAttendancePage'
import { formatDuration, formatTime, fromZonedInput, toZonedInput } from './format'
import { hasCabinetInDevelopment, homeFor, isStaffOnlyRole } from '@/lib/roles'

import { PersonalAttendancePage } from './PersonalAttendancePage'
import { personalPathFor, workspaceFor } from './roles'
import { parseOfficeQr } from './scanUrl'

const api = vi.mocked(staffAttendanceApi)
const TZ = 'Asia/Bishkek'
const CODE = 'Abc123_office-XYZ'

const employee = { id: 7, full_name: 'Айбек Тренер', username: 'aibek', role: 'teacher' as const, role_label: 'Тренер', photo_url: null }

function emptyRow(over: Partial<DayRow> = {}): DayRow {
  return {
    key: '7:2026-10-21', employee, date: '2026-10-21', status: 'not_arrived', status_label: 'Ещё не пришёл', check_in: null,
    check_out: null, duration_seconds: null, late_minutes: 0, is_late: false, is_adjusted: false,
    expected_start: '2026-10-21T09:00:00+06:00', expected_end: '2026-10-21T18:00:00+06:00', sessions_count: 0,
    last_session_id: null, locations: [], sessions: [], ...over,
  }
}

const session: WorkSession = {
  id: 11, work_date: '2026-10-21', checked_in_at: '2026-10-21T09:25:00+06:00', checked_out_at: null, status: 'open',
  status_label: 'На работе', source: 'qr', duration_seconds: 60, expected_start: '2026-10-21T09:00:00+06:00',
  late_minutes: 25, is_adjusted: false, location: { id: 1, name: 'Главный офис' }, check_in_distance_m: 12.4, check_out_distance_m: null,
}

const status: MyStatus = {
  employee, state: 'not_arrived', next_action: 'check_in', server_time: '2026-10-21T09:24:00+06:00', timezone: TZ,
  today: emptyRow(), open_session: null, stale_session: null,
  access: { can_view_reports: false, can_adjust: false, can_manage: false },
}

function axiosError(statusCode: number, data: unknown): AxiosError {
  return new AxiosError('fail', 'ERR', undefined, undefined, { status: statusCode, data } as AxiosResponse)
}

function mockGeolocation(impl: (ok: PositionCallback, fail: PositionErrorCallback) => void) {
  Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition: vi.fn(impl) } })
}

beforeEach(() => {
  vi.clearAllMocks()
  api.myStatus.mockResolvedValue(status)
  api.myStats.mockResolvedValue({
    year: 2026, month: 10, days_present: 14, work_days: 18, late_days: 2, late_minutes_total: 35, no_check_in_days: 1,
    no_check_out_days: 0, adjusted_days: 0, total_seconds: 14 * 8 * 3600, average_seconds: 8 * 3600,
  })
  api.myHistory.mockResolvedValue({ count: 1, next: null, previous: null, results: [{ ...session, checked_out_at: '2026-10-21T18:00:00+06:00', status: 'closed', status_label: 'Завершена', duration_seconds: 8 * 3600 + 35 * 60 }] })
})

afterEach(() => {
  Reflect.deleteProperty(navigator, 'geolocation')
})

describe('QR-ссылка офиса', () => {
  it('принимает HTTPS-ссылку на страницу отметки с кодом офиса', () => {
    expect(parseOfficeQr(`https://lms.okurmenkids.com/attendance/scan?office=${CODE}`, 'https://lms.okurmenkids.com')).toEqual({ ok: true, code: CODE })
    expect(parseOfficeQr(`http://localhost:5173/attendance/scan/?office=${CODE}`, 'http://localhost:5173')).toEqual({ ok: true, code: CODE })
  })

  it('отклоняет чужие и небезопасные ссылки', () => {
    expect(parseOfficeQr('просто текст', 'https://a.kg').ok).toBe(false)
    expect(parseOfficeQr(`http://evil.example/attendance/scan?office=${CODE}`, 'https://a.kg').ok).toBe(false)
    expect(parseOfficeQr(`https://a.kg/login?office=${CODE}`, 'https://a.kg').ok).toBe(false)
    expect(parseOfficeQr('https://a.kg/attendance/scan?office=<script>', 'https://a.kg').ok).toBe(false)
    expect(parseOfficeQr('https://a.kg/attendance/scan', 'https://a.kg').ok).toBe(false)
  })
})

describe('время в часовом поясе офиса', () => {
  it('показывает и вводит время по Бишкеку независимо от пояса устройства', () => {
    expect(formatTime('2026-10-21T03:05:00Z', TZ)).toBe('09:05')
    expect(fromZonedInput('2026-10-21T09:05', TZ)).toBe('2026-10-21T03:05:00.000Z')
    expect(toZonedInput('2026-10-21T03:05:00Z', TZ)).toBe('2026-10-21T09:05')
    expect(fromZonedInput('не дата', TZ)).toBeNull()
    expect(formatDuration(8 * 3600 + 35 * 60)).toBe('8 ч 35 мин')
    expect(formatDuration(null)).toBe('—')
  })
})

describe('роли с базовым доступом (ДОП, РОП, РОМ, операционный директор, HR, продажи, маркетинг)', () => {
  const STAFF = ['dop', 'rop', 'rom', 'operations_director', 'sales_manager', 'marketing'] as const

  it('после входа ведут на страницу отметки, без перехода в LMS', () => {
    for (const role of STAFF) {
      expect(hasCabinetInDevelopment(role)).toBe(true)
      expect(isStaffOnlyRole(role)).toBe(true)
      expect(homeFor(role, '/app/dashboard')).toBe('/attendance/staff')
      expect(homeFor(role, '/attendance/scan?office=abc')).toBe('/attendance/scan?office=abc')
      expect(personalPathFor(role)).toBe('/attendance/staff')
      expect(workspaceFor(role)).toBeNull()
    }
  })

  it('HR-менеджер после входа попадает в HR-кабинет', () => {
    expect(isStaffOnlyRole('hr_manager')).toBe(true)
    expect(hasCabinetInDevelopment('hr_manager')).toBe(false)
    expect(homeFor('hr_manager', '/app/dashboard')).toBe('/hr')
    expect(homeFor('hr_manager', '/hr/candidates/5')).toBe('/hr/candidates/5')
    expect(homeFor('hr_manager', '/attendance/scan?office=abc')).toBe('/attendance/scan?office=abc')
    expect(personalPathFor('hr_manager')).toBe('/attendance/staff')
    expect(workspaceFor('hr_manager')).toEqual({ to: '/hr', label: 'HR-кабинет' })
  })

  it('не меняют маршруты существующих ролей', () => {
    expect(isStaffOnlyRole('accountant')).toBe(false)
    expect(homeFor('accountant', '/app/dashboard')).toBe('/accounting')
    expect(homeFor('team_lead', '/app/dashboard')).toBe('/app/dashboard')
    expect(personalPathFor('teacher')).toBe('/attendance/teacher')
    expect(personalPathFor('director')).toBe('/attendance/office')
    expect(workspaceFor('assistant')).toEqual({ to: '/assistant', label: 'Assistant Workspace' })
  })

  it('видят сообщение о кабинете в разработке и могут отметиться', async () => {
    renderWithProviders(<PersonalAttendancePage variant="staff" />)
    expect(await screen.findByText('Ваш личный кабинет находится в разработке')).toBeInTheDocument()
    expect(screen.getByText('Приход и уход — сотрудник')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Сканировать QR/ })).toBeInTheDocument()
  })

  it('HR видит свою отметку без сообщения о кабинете', async () => {
    renderWithProviders(<PersonalAttendancePage variant="staff" cabinetNotice={false} />)
    expect(await screen.findByText('Приход и уход — сотрудник')).toBeInTheDocument()
    expect(screen.queryByText('Ваш личный кабинет находится в разработке')).not.toBeInTheDocument()
  })

  it('у остальных ролей сообщения нет', async () => {
    renderWithProviders(<PersonalAttendancePage variant="teacher" />)
    expect(await screen.findByRole('heading', { name: 'Айбек Тренер' })).toBeInTheDocument()
    expect(screen.queryByText('Ваш личный кабинет находится в разработке')).not.toBeInTheDocument()
  })
})

describe('личная страница отметки', () => {
  it('показывает сотрудника, статус, кнопку сканирования, статистику и историю', async () => {
    renderWithProviders(<PersonalAttendancePage variant="teacher" />)
    expect(await screen.findByRole('heading', { name: 'Айбек Тренер' })).toBeInTheDocument()
    expect(screen.getByText('Ещё не пришёл')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Сканировать QR/ })).toBeInTheDocument()
    expect(await screen.findByText('14 из 18')).toBeInTheDocument()
    expect(await screen.findByText('8 ч 35 мин')).toBeInTheDocument()
    expect(screen.getByText('Опоздание 25 мин')).toBeInTheDocument()
    expect(api.myHistory).toHaveBeenCalledWith({ page: 1 })
  })

  it('при открытии по QR-ссылке проверяет офис, берёт геолокацию и показывает подтверждение только после ответа сервера', async () => {
    api.verifyOffice.mockResolvedValue({ code: CODE, name: 'Главный офис', address: '', radius_m: 100 })
    mockGeolocation((ok) => ok({ coords: { latitude: 42.8855, longitude: 74.6031, accuracy: 12 } } as GeolocationPosition))
    let resolveCheckIn: (value: MarkResult) => void = () => undefined
    api.checkIn.mockReturnValue(new Promise((resolve) => { resolveCheckIn = resolve }))

    renderWithProviders(<PersonalAttendancePage variant="teacher" presetCode={CODE} />)
    expect(await screen.findByText('Регистрируем приход…')).toBeInTheDocument()
    expect(screen.queryByText('Приход успешно зарегистрирован')).not.toBeInTheDocument()

    const payload = api.checkIn.mock.calls[0][0]
    expect(payload).toMatchObject({ location_code: CODE, latitude: 42.8855, longitude: 74.6031, accuracy: 12 })
    expect(payload.idempotency_key).toMatch(/^[0-9a-f-]{36}$/)
    expect(payload).not.toHaveProperty('user')
    expect(api.verifyOffice).toHaveBeenCalledWith(CODE)

    resolveCheckIn({
      event: 'check_in', replayed: false, employee, occurred_at: '2026-10-21T09:25:00+06:00', timezone: TZ,
      location: { name: 'Главный офис' }, distance_m: 12.4, session, closed_stale_session: null,
    })
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('Приход успешно зарегистрирован')).toBeInTheDocument()
    expect(within(dialog).getByText('09:25')).toBeInTheDocument()
    expect(within(dialog).getByText('Главный офис')).toBeInTheDocument()
    expect(within(dialog).getByText('12 м')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Вернуться в кабинет' })).toBeInTheDocument()
  })

  it('показывает причину отказа сервера и не показывает успех', async () => {
    api.verifyOffice.mockResolvedValue({ code: CODE, name: 'Главный офис', address: '', radius_m: 100 })
    mockGeolocation((ok) => ok({ coords: { latitude: 42.9, longitude: 74.7, accuracy: 10 } } as GeolocationPosition))
    api.checkIn.mockRejectedValue(axiosError(400, { detail: 'Вы находитесь в 850 м от офиса «Главный офис».', code: 'out_of_range' }))

    renderWithProviders(<PersonalAttendancePage variant="teacher" presetCode={CODE} />)
    expect(await screen.findByText('Вы находитесь в 850 м от офиса «Главный офис».')).toBeInTheDocument()
    expect(screen.getByText('Отметка не выполнена')).toBeInTheDocument()
    expect(screen.queryByText('Приход успешно зарегистрирован')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Повторить попытку' })).toBeInTheDocument()
  })

  it('при запрете геолокации не отправляет отметку и предлагает повторить', async () => {
    api.verifyOffice.mockResolvedValue({ code: CODE, name: 'Главный офис', address: '', radius_m: 100 })
    mockGeolocation((_ok, fail) => fail({ code: 1, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3, message: '' } as GeolocationPositionError))

    renderWithProviders(<PersonalAttendancePage variant="teacher" presetCode={CODE} />)
    expect(await screen.findByText(/Доступ к геолокации запрещён/)).toBeInTheDocument()
    expect(api.checkIn).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Повторить попытку' }))
    await waitFor(() => expect(navigator.geolocation.getCurrentPosition).toHaveBeenCalledTimes(2))
  })

  it('неизвестный офис из QR — понятная ошибка без отметки', async () => {
    api.verifyOffice.mockRejectedValue(axiosError(404, { detail: 'QR-код не относится ни к одному офису OkurmenKIDS.', code: 'location_not_found' }))
    renderWithProviders(<PersonalAttendancePage variant="teacher" presetCode={CODE} />)
    expect(await screen.findByText('QR-код не относится ни к одному офису OkurmenKIDS.')).toBeInTheDocument()
    expect(api.checkIn).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Сканировать снова' })).toBeInTheDocument()
  })
})

describe('административная панель', () => {
  const meta: AdminMeta = {
    timezone: TZ, today: '2026-10-21',
    roles: [{ value: 'teacher', label: 'Тренер' }, { value: 'assistant', label: 'Ассистент' }],
    statuses: [{ value: 'late', label: 'Опоздание' }, { value: 'at_work', label: 'На работе' }],
    locations: [{ id: 1, name: 'Главный офис', is_active: true }],
    access: { can_view_reports: true, can_adjust: true, can_manage: true, scope: 'all' },
  }
  const overview: Overview = {
    date: '2026-10-21', total_employees: 12, arrived: 9, at_work: 7, late: 3, finished: 2, not_arrived: 2, no_check_in: 1,
    no_check_out: 0, day_off: 0, not_tracked: 0, adjusted: 1,
  }

  it('показывает реальные показатели и строки таблицы, фильтр статуса уходит на сервер', async () => {
    api.meta.mockResolvedValue(meta)
    api.overview.mockResolvedValue(overview)
    api.records.mockResolvedValue({
      count: 1, next: null, previous: null,
      results: [emptyRow({ status: 'at_work', status_label: 'На работе', check_in: session.checked_in_at, duration_seconds: 3600, late_minutes: 25, is_late: true, sessions_count: 1, last_session_id: 11, sessions: [session] })],
    })

    renderWithProviders(<AdminAttendancePage />)
    expect(await screen.findByRole('heading', { name: 'Учёт посещаемости' })).toBeInTheDocument()
    expect(screen.getByText('Приход, уход и рабочее время сотрудников')).toBeInTheDocument()
    expect(await screen.findByText('12')).toBeInTheDocument()
    expect(screen.getByText('Сейчас на работе').closest('div')?.parentElement).toHaveTextContent('7')
    expect(screen.getByText('Нет отметки прихода').closest('div')?.parentElement).toHaveTextContent('3')
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Айбек Тренер')).toBeInTheDocument()
    expect(within(table).getByText('09:25')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Статус'), 'late')
    await waitFor(() => expect(api.records).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'late', page: 1, date: '2026-10-21' })))
  })

  it('без прав на отчёты уводит в личный кабинет', async () => {
    api.meta.mockRejectedValue(axiosError(403, { detail: 'Отчёты посещаемости сотрудников вам недоступны.' }))
    renderWithProviders(
      <Routes>
        <Route path="/admin/attendance" element={<AdminAttendancePage />} />
        <Route path="/attendance" element={<p>Личный кабинет</p>} />
      </Routes>,
      { route: '/admin/attendance' },
    )
    expect(await screen.findByText('Личный кабинет')).toBeInTheDocument()
    expect(api.records).not.toHaveBeenCalled()
  })
})

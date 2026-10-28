import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { HREmployee, HRRoleOption } from '@/types/hr'

vi.mock('@/api/hr', () => ({
  hrApi: { meta: vi.fn(), list: vi.fn(), create: vi.fn(), update: vi.fn(), setPassword: vi.fn(), setActive: vi.fn() },
}))

const auth = vi.hoisted(() => ({ role: 'hr_manager' }))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 1, role: auth.role, first_name: 'Айгуль', last_name: 'HR' }, status: 'authenticated', logout: vi.fn() }),
}))

import { hrApi } from '@/api/hr'

import { HrEmployeesPage } from './EmployeesPage'

const api = vi.mocked(hrApi)

const rop: HREmployee = {
  id: 5, username: 'rop', email: 'rop@okurmen.kg', first_name: 'Азамат', last_name: 'Иванов', full_name: 'Азамат Иванов',
  role: 'rop', role_label: 'РОП', is_active: true, can_manage: true, created_at: '2026-10-01T10:00:00+06:00', last_login: null,
}

const ROLES: HRRoleOption[] = [
  { value: 'teacher', label: 'Тренер' }, { value: 'team_lead', label: 'Руководитель тренеров (Team Lead)' },
  { value: 'assistant', label: 'Ассистент' }, { value: 'rop', label: 'РОП — руководитель отдела продаж' },
  { value: 'hr_manager', label: 'HR-менеджер' },
  { value: 'sales_manager', label: 'Менеджер по продажам' }, { value: 'marketing', label: 'Маркетинг' },
]

beforeEach(() => {
  vi.clearAllMocks()
  auth.role = 'hr_manager'
  api.meta.mockResolvedValue({
    roles: ROLES,
    protected_roles: [
      { value: 'director', label: 'Директор' }, { value: 'accountant', label: 'Бухгалтер' },
      { value: 'dop', label: 'ДОП — директор отдела продаж' }, { value: 'operations_director', label: 'Операционный директор' },
    ],
  })
  api.list.mockResolvedValue({ count: 1, next: null, previous: null, results: [rop] })
})

describe('раздел «Сотрудники» HR', () => {
  it('показывает сотрудников, должность, статус и дату создания', async () => {
    renderWithProviders(<HrEmployeesPage />)
    expect(await screen.findByText('Азамат Иванов')).toBeInTheDocument()
    const row = screen.getByText('Азамат Иванов').closest('tr') as HTMLElement
    expect(within(row).getByText('РОП')).toBeInTheDocument()
    expect(within(row).getByText('Активен')).toBeInTheDocument()
    expect(within(row).getByText('01.10.2026')).toBeInTheDocument()
    expect(await screen.findByText(/Директор, Бухгалтер, ДОП — директор отдела продаж, Операционный директор/)).toBeInTheDocument()
  })

  it('фильтры поиска, должности и статуса уходят на сервер', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HrEmployeesPage />)
    await screen.findByText('Азамат Иванов')
    await user.type(screen.getByLabelText('Поиск сотрудника'), 'Аз')
    await user.selectOptions(screen.getByLabelText('Должность'), 'rop')
    await user.selectOptions(screen.getByLabelText('Статус'), 'false')
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith({ search: 'Аз', role: 'rop', is_active: 'false', ordering: '-created_at', page: 1 }))
  })

  it('в форме создания — все разрешённые роли и ни одной защищённой', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HrEmployeesPage />)
    await screen.findByText('Азамат Иванов')
    await user.click(screen.getByRole('button', { name: /Новый сотрудник/ }))
    const options = within(screen.getByLabelText('Должность *')).getAllByRole('option') as HTMLOptionElement[]
    expect(options.map((o) => o.value).filter(Boolean)).toEqual(ROLES.map((r) => r.value))
    for (const name of ['Директор', 'Бухгалтер', 'ДОП — директор отдела продаж', 'Операционный директор']) {
      expect(within(screen.getByLabelText('Должность *')).queryByRole('option', { name })).not.toBeInTheDocument()
    }
  })

  it('при редактировании роль «Тренер» нельзя ни снять, ни назначить', async () => {
    const user = userEvent.setup()
    const teacher: HREmployee = { ...rop, id: 6, full_name: 'Бакыт Тренер', role: 'teacher', role_label: 'Тренер' }
    api.list.mockResolvedValue({ count: 2, next: null, previous: null, results: [rop, teacher] })
    renderWithProviders(<HrEmployeesPage />)
    await user.click(await screen.findByRole('button', { name: 'Изменить Азамат Иванов' }))
    let values = (within(screen.getByLabelText('Должность *')).getAllByRole('option') as HTMLOptionElement[]).map((o) => o.value)
    expect(values).not.toContain('teacher')
    expect(values).toContain('team_lead')
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    await user.click(screen.getByRole('button', { name: 'Изменить Бакыт Тренер' }))
    values = (within(screen.getByLabelText('Должность *')).getAllByRole('option') as HTMLOptionElement[]).map((o) => o.value).filter(Boolean)
    expect(values).toEqual(['teacher'])
  })

  it('учётная запись коллеги-HR — только просмотр, без действий', async () => {
    const peer: HREmployee = { ...rop, id: 7, full_name: 'Динара HR', role: 'hr_manager', role_label: 'HR-менеджер', can_manage: false }
    api.list.mockResolvedValue({ count: 1, next: null, previous: null, results: [peer] })
    renderWithProviders(<HrEmployeesPage />)
    const row = (await screen.findByText('Динара HR')).closest('tr') as HTMLElement
    expect(within(row).getByText('Только просмотр')).toBeInTheDocument()
    expect(within(row).queryByRole('button')).not.toBeInTheDocument()
  })

  it('создаёт сотрудника с разрешённой ролью из списка сервера', async () => {
    const user = userEvent.setup()
    api.create.mockResolvedValue({ ...rop, id: 9 })
    renderWithProviders(<HrEmployeesPage />)
    await screen.findByText('Азамат Иванов')
    await user.click(screen.getByRole('button', { name: /Новый сотрудник/ }))
    const roleSelect = screen.getByLabelText('Должность *')
    await user.type(screen.getByLabelText('Имя *'), 'Нурлан')
    await user.type(screen.getByLabelText('Логин *'), 'nurlan')
    await user.type(screen.getByLabelText('Email *'), 'nurlan@okurmen.kg')
    await user.selectOptions(roleSelect, 'team_lead')
    await user.type(screen.getByLabelText('Пароль *'), 'Str0ngPassw0rd!')
    await user.type(screen.getByLabelText('Повторите пароль *'), 'Str0ngPassw0rd!')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(api.create).toHaveBeenCalledWith({
      username: 'nurlan', email: 'nurlan@okurmen.kg', first_name: 'Нурлан', last_name: '', role: 'team_lead',
      password: 'Str0ngPassw0rd!', password_confirm: 'Str0ngPassw0rd!',
    }))
  })

  it('показывает отказ сервера', async () => {
    const user = userEvent.setup()
    const { AxiosError } = await import('axios')
    api.setPassword.mockRejectedValue(new AxiosError('fail', 'ERR', undefined, undefined, {
      status: 403, data: { detail: 'Этот сотрудник вне полномочий HR: управлять его учётной записью нельзя.' },
    } as never))
    renderWithProviders(<HrEmployeesPage />)
    await screen.findByText('Азамат Иванов')
    await user.click(screen.getByRole('button', { name: 'Пароль Азамат Иванов' }))
    await user.type(screen.getByLabelText('Новый пароль *'), 'An0therStr0ng!')
    await user.type(screen.getByLabelText('Повторите пароль *'), 'An0therStr0ng!')
    await user.click(screen.getByRole('button', { name: 'Сохранить пароль' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('вне полномочий HR')
  })

  it('деактивирует после подтверждения', async () => {
    const user = userEvent.setup()
    api.setActive.mockResolvedValue({ ...rop, is_active: false })
    renderWithProviders(<HrEmployeesPage />)
    await screen.findByText('Азамат Иванов')
    await user.click(screen.getByRole('button', { name: 'Деактивировать' }))
    expect(screen.getByText(/История посещаемости и данные сохранятся/)).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Деактивировать' }))
    await waitFor(() => expect(api.setActive).toHaveBeenCalledWith(5, false))
  })

  it('другим ролям раздел недоступен', () => {
    auth.role = 'rop'
    renderWithProviders(<HrEmployeesPage />)
    expect(api.list).not.toHaveBeenCalled()
  })
})

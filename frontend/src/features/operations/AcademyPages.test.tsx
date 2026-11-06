import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { AcademyGroupsResponse, AcademyMeta, AcademyMonthlyResponse, AcademyStudentProfile, AcademyStudentsResponse } from '@/types/operationsAcademy'

vi.mock('@/api/operations', () => ({
  operationsApi: {
    meta: vi.fn().mockResolvedValue({ periods: [], departments: [], roles: [], employees: [] }),
    academyMeta: vi.fn(), academyGroups: vi.fn(), academyStudents: vi.fn(), academyStudent: vi.fn(), academyMonthly: vi.fn(),
  },
  tasksApi: {},
  notificationsApi: { unreadCount: vi.fn().mockResolvedValue({ count: 0 }), list: vi.fn().mockResolvedValue({ count: 0, results: [], next: null, previous: null }) },
  workReportsApi: {},
}))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 7, role: 'operations_director', first_name: 'Олег', last_name: 'Директоров' }, status: 'authenticated', logout: vi.fn() }),
}))

import { operationsApi } from '@/api/operations'

import { OperationsAcademyGroupsPage, OperationsAcademyMonthlyPage, OperationsAcademyStudentPage, OperationsAcademyStudentsPage } from './AcademyPages'
import { OperationsLayout } from './OperationsLayout'

const ops = vi.mocked(operationsApi)
const filters = { period: 'this_month' as const, label: 'Этот месяц', start: '2026-11-01', end: '2026-11-30' }
const META: AcademyMeta = {
  programs: [{ id: 1, name: 'Okurmen 144' }], groups: [{ id: 3, name: 'Group A' }], teachers: [{ id: 9, name: 'Айбек Тренер' }], subjects: [],
  group_statuses: [{ value: 'active', label: 'Активна' }], student_statuses: [{ value: 'active', label: 'Активен' }], thresholds: {}, finance_visible: true,
}

beforeEach(() => {
  vi.clearAllMocks()
  ops.academyMeta.mockResolvedValue(META)
})

describe('раздел «Академия» кабинета операционного директора', () => {
  it('в меню есть раздел «Академия» с шестью пунктами', () => {
    renderWithProviders(<Routes><Route path="/operations" element={<OperationsLayout />}><Route index element={<p>Dashboard</p>} /></Route></Routes>, { route: '/operations' })
    const section = screen.getAllByRole('group', { name: 'Академия' })[0]
    expect(within(section).getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
      ['Группы', '/operations/academy/groups'], ['Студенты', '/operations/academy/students'],
      ['Успеваемость', '/operations/academy/performance'], ['Месячные результаты', '/operations/academy/monthly'],
      ['Посещаемость групп', '/operations/attendance'],
      ['Сводка посещаемости', '/operations/academy/attendance'],
    ])
  })

  it('группы: данные сервера, фильтр программы уходит в запрос', async () => {
    const response: AcademyGroupsResponse = {
      filters, summary: { groups: 1, active: 1, students: 12, average_attendance: 87.5, attention: 0 }, count: 1, page: 1, pages: 1, page_size: 25,
      results: [{
        id: 3, name: 'Group A', program: 'Okurmen 144', program_id: 1, status: 'active', status_display: 'Активна', start_date: '2026-09-01',
        trainers: [{ id: 9, name: 'Айбек Тренер' }], trainer_names: 'Айбек Тренер', students: { total: 12, active: 12, left: 0, new: 1, returned: 0 },
        lessons: { total: 8, held: 8, cancelled: 0, due: 8 }, attendance_rate: 87.5, homework_rate: 70, test_score_rate: 80, progress_rate: 75,
        kpi: 78, kpi_level: 'attention', has_data: true, plan: { completed: 40, planned: 144, remaining: 104, progress: 27.8 },
      }],
    }
    ops.academyGroups.mockResolvedValue(response)
    renderWithProviders(<OperationsAcademyGroupsPage />, { route: '/operations/academy/groups?period=this_month' })
    const row = (await screen.findByRole('link', { name: 'Group A' })).closest('tr') as HTMLElement
    expect(row).toHaveTextContent('Айбек Тренер')
    expect(row).toHaveTextContent('104')
    expect(within(row).getByRole('link', { name: 'Group A' })).toHaveAttribute('href', '/operations/academy/groups/3')
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Программа' }), '1')
    await waitFor(() => expect(ops.academyGroups).toHaveBeenLastCalledWith(expect.objectContaining({ program: '1', period: 'this_month' })))
  })

  it('студенты: колонки договора, оплат и долга из оплаты обучения', async () => {
    const response: AcademyStudentsResponse = {
      filters, finance_visible: true, count: 1, page: 1, pages: 1, page_size: 25,
      results: [{ id: 5, name: 'Айжан Студент', status: 'active', status_display: 'Активен', group: { id: 3, name: 'Group A' }, program: 'Okurmen 144',
        trainers: ['Айбек Тренер'], enrollment_date: '2026-09-01', attendance_rate: 90, homework_rate: 80, average_score: 8.5, progress_rate: 70, level: 'good',
        finance: { contracts: 1, contract_amount: '36000.00', paid: '12000.00', debt: '24000.00' } }],
    }
    ops.academyStudents.mockResolvedValue(response)
    renderWithProviders(<OperationsAcademyStudentsPage />, { route: '/operations/academy/students' })
    const row = (await screen.findByRole('link', { name: 'Айжан Студент' })).closest('tr') as HTMLElement
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent)
    expect(headers).toEqual(['Студент', 'Группа', 'Программа', 'Тренер', 'Зачислен', 'Договор', 'Оплачено', 'Долг', 'Посещаемость', 'Успеваемость', 'Статус'])
    expect(row).toHaveTextContent(/36\s000/)
    expect(row).toHaveTextContent(/24\s000/)
  })

  it('профиль студента: договор и оплаты только для просмотра — без кнопок оплаты и изменения', async () => {
    const profile: AcademyStudentProfile = {
      filters,
      student: { id: 5, name: 'Айжан Студент', status: 'active', status_display: 'Активен', enrollment_date: '2026-09-01', group: { id: 3, name: 'Group A', status_display: 'Активна' }, program: 'Okurmen 144', trainers: [{ id: 9, name: 'Айбек Тренер', subject: 'IT' }] },
      academic: {
        attendance_total: 10, attended: 9, attendance_rate: 90, homework_results: 5, homework_submitted: 4, homework_rate: 80, average_score: 8.5, progress_rate: 70, level: 'good',
        period: null, lessons: [], tests: [], xp: { attendance: 90, homework: 40, tests: 12, total: 142 }, achievements: [{ kind: 'scholarship', title: 'Стипендия — 1 место', date: '2026-10-01', amount: '2000.00', period: 'Октябрь' }],
        assessments: { tests: { attempts: 2, passed: 2, pass_rate: 100, average_score: 85 }, exams: { attempts: 1, passed: 1, pass_rate: 100, average_score: 77 }, sessions: [] },
        badges_tracked: false,
      },
      history: [],
      finance: {
        contracts: [{ id: 1, plan: 'IT 12', program: 'Okurmen 144', subject: 'IT', status: 'active', status_display: 'Активен', start_date: '2026-09-01', discount_reason: 'Брат',
          original: '40000.00', discount: '4000.00', final: '36000.00', paid: '12000.00', debt: '24000.00', due_now: '0.00', overdue: '0.00', paid_in_full: false }],
        payments: [{ id: 2, date: '2026-09-05', amount: '12000.00', kind: 'payment', kind_display: 'Оплата', method_display: 'Наличные', status: 'confirmed', status_display: 'Подтверждён', group: 'Group A', program: 'Okurmen 144', comment: 'Первый месяц' }],
      },
    }
    ops.academyStudent.mockResolvedValue(profile)
    renderWithProviders(<Routes><Route path="/operations/academy/students/:id" element={<OperationsAcademyStudentPage />} /></Routes>, { route: '/operations/academy/students/5' })
    expect(await screen.findByRole('heading', { name: 'Айжан Студент' })).toBeInTheDocument()
    expect(ops.academyStudent).toHaveBeenCalledWith(5, expect.objectContaining({ period: 'this_month' }))
    const finance = screen.getByText('Договор и оплаты (только просмотр)').closest('section') as HTMLElement
    for (const label of ['Стоимость по договору', 'Скидка', 'Итого по договору', 'Оплачено', 'Долг']) expect(within(finance).getByText(label)).toBeInTheDocument()
    expect(finance).toHaveTextContent('Первый месяц')
    expect(within(finance).queryAllByRole('button')).toHaveLength(0)
    expect(screen.getByText('142')).toBeInTheDocument()
    expect(screen.getByText(/Стипендия — 1 место/)).toBeInTheDocument()
  })

  it('месячные результаты: показатели и студенты, требующие внимания, с причинами', async () => {
    const response: AcademyMonthlyResponse = {
      filters,
      indicators: { active_students: 120, new_students: 8, left_students: 2, returned_students: 1, transferred_students: 3, attendance_rate: 88, homework_rate: 71,
        academic_performance: 74, test_average: 81, kpi: 77, achievements: 5, xp: 15000, attention: 1, groups: 10 },
      dynamics: [{ month: '2026-10', attendance_rate: 86, homework_rate: 69, test_average: 80, progress_rate: 72, kpi: 75, active: 118, new: 6, left: 3 },
        { month: '2026-11', attendance_rate: 88, homework_rate: 71, test_average: 81, progress_rate: 74, kpi: 77, active: 120, new: 8, left: 2 }],
      groups: [], thresholds: { low_attendance: 60, low_homework: 40, frequent_absences: 3, low_test_score: 50, decline_points: 15 }, badges_tracked: false,
      attention: [{ id: 5, name: 'Бектур Студент', group: 'Group A', group_id: 3, status: 'low', status_display: 'Низкая активность', attendance_rate: 40, homework_rate: 20,
        reasons: ['Частые пропуски: 4 за период (порог 3)', 'Низкая посещаемость: 40% (порог 60%)'] }],
    }
    ops.academyMonthly.mockResolvedValue(response)
    renderWithProviders(<OperationsAcademyMonthlyPage />, { route: '/operations/academy/monthly' })
    expect(await screen.findByText('Переведены между группами')).toBeInTheDocument()
    const row = screen.getByRole('link', { name: 'Бектур Студент' }).closest('tr') as HTMLElement
    expect(row).toHaveTextContent('Частые пропуски: 4 за период (порог 3)')
    expect(row).toHaveTextContent('Низкая посещаемость: 40% (порог 60%)')
    expect(screen.getByText('Требуют внимания · 1')).toBeInTheDocument()
  })
})

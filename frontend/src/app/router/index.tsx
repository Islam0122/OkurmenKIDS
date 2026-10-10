import { createBrowserRouter, Navigate } from 'react-router-dom'

import { AppLayout } from '@/app/layouts/AppLayout'
import { AccessDeniedPage } from '@/features/auth/AccessDeniedPage'
import { LoginPage } from '@/features/auth/LoginPage'
import { HOME_PATH } from '@/lib/appMode'

import { NotFoundPage } from './NotFoundPage'
import { ProtectedRoute } from './ProtectedRoute'
import { RequireRoles } from './RequireRoles'
import { RouteErrorPage } from './RouteErrorPage'

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to={HOME_PATH} replace />, errorElement: <RouteErrorPage /> },
  { path: '/login', element: <LoginPage />, errorElement: <RouteErrorPage /> },
  {
    // Короткий адрес «Моей зарплаты»: ведёт на страницу в кабинете своей роли.
    path: '/my-salary',
    element: <ProtectedRoute />,
    errorElement: <RouteErrorPage />,
    children: [{ index: true, lazy: async () => ({ Component: (await import('./MySalaryRedirect')).MySalaryRedirect }) }],
  },
  { path: '/access-denied', element: <AccessDeniedPage />, errorElement: <RouteErrorPage /> },
  {
    path: '/app',
    element: <ProtectedRoute />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <Navigate to="/app/dashboard" replace /> },
          {
            path: 'dashboard',
            lazy: async () => {
              const { DashboardPage } = await import('@/features/dashboard/DashboardPage')
              return { Component: DashboardPage }
            },
          },
          {
            path: 'schedule',
            lazy: async () => {
              const { SchedulePage } = await import('@/features/schedule/SchedulePage')
              return { Component: SchedulePage }
            },
          },
          {
            // Academy-wide sections: Admin and Team Lead (backend: IsAdminOrTeamLeadReadOnly).
            element: <RequireRoles roles={['admin', 'team_lead']} />,
            children: [
              {
                path: 'trainers',
                lazy: async () => {
                  const { TrainersListPage } = await import('@/features/trainers/TrainersListPage')
                  return { Component: TrainersListPage }
                },
              },
              {
                path: 'trainers/:id',
                lazy: async () => {
                  const { TrainerDetailPage } = await import('@/features/trainers/TrainerDetailPage')
                  return { Component: TrainerDetailPage }
                },
              },
              {
                path: 'tests',
                lazy: async () => {
                  const { TestsBankPage } = await import('@/features/exams/TestsBankPage')
                  return { Component: TestsBankPage }
                },
              },
              {
                path: 'analytics',
                lazy: async () => {
                  const { AnalyticsPage } = await import('@/features/analytics/AnalyticsPage')
                  return { Component: AnalyticsPage }
                },
              },
              {
                // Рабочий журнал Team Lead (backend: apps.worklog, author-only writes).
                path: 'worklog',
                lazy: async () => {
                  const { WorklogPage } = await import('@/features/worklog/WorklogPage')
                  return { Component: WorklogPage }
                },
              },
              {
                path: 'worklog/reports/:id',
                lazy: async () => {
                  const { ReportPage } = await import('@/features/worklog/ReportPage')
                  return { Component: ReportPage }
                },
              },
            ],
          },
          {
            path: 'groups',
            lazy: async () => {
              const { GroupsListPage } = await import('@/features/groups/GroupsListPage')
              return { Component: GroupsListPage }
            },
          },
          {
            path: 'groups/:id',
            lazy: async () => {
              const { GroupDetailPage } = await import('@/features/groups/GroupDetailPage')
              return { Component: GroupDetailPage }
            },
          },
          {
            path: 'students',
            lazy: async () => {
              const { StudentsListPage } = await import('@/features/students/StudentsListPage')
              return { Component: StudentsListPage }
            },
          },
          {
            path: 'students/:id',
            lazy: async () => {
              const { StudentDetailPage } = await import('@/features/students/StudentDetailPage')
              return { Component: StudentDetailPage }
            },
          },
          {
            path: 'lessons',
            lazy: async () => {
              const { LessonsListPage } = await import('@/features/lessons/LessonsListPage')
              return { Component: LessonsListPage }
            },
          },
          {
            path: 'lessons/:id',
            lazy: async () => {
              const { LessonDetailPage } = await import('@/features/lessons/LessonDetailPage')
              return { Component: LessonDetailPage }
            },
          },
          {
            path: 'attendance',
            lazy: async () => {
              const { AttendancePage } = await import('@/features/attendance/AttendancePage')
              return { Component: AttendancePage }
            },
          },
          {
            path: 'homework',
            lazy: async () => {
              const { HomeworkListPage } = await import('@/features/homework/HomeworkListPage')
              return { Component: HomeworkListPage }
            },
          },
          {
            path: 'monitoring',
            lazy: async () => {
              const { MonitoringPage } = await import('@/features/monitoring/MonitoringPage')
              return { Component: MonitoringPage }
            },
          },
          {
            path: 'exams',
            lazy: async () => {
              const { ExamsListPage } = await import('@/features/exams/ExamsListPage')
              return { Component: ExamsListPage }
            },
          },
          {
            path: 'exams/:id',
            lazy: async () => {
              const { ExamDetailPage } = await import('@/features/exams/ExamDetailPage')
              return { Component: ExamDetailPage }
            },
          },
          {
            path: 'homework/:id',
            lazy: async () => {
              const { HomeworkDetailPage } = await import('@/features/homework/HomeworkDetailPage')
              return { Component: HomeworkDetailPage }
            },
          },
          {
            path: 'kpi',
            lazy: async () => {
              const { KPIPage } = await import('@/features/kpi/KPIPage')
              return { Component: KPIPage }
            },
          },
          {
            path: 'control',
            lazy: async () => {
              const { ControlPage } = await import('@/features/control/ControlPage')
              return { Component: ControlPage }
            },
          },
          {
            path: 'reports',
            lazy: async () => {
              const { ReportsListPage } = await import('@/features/reports/ReportsListPage')
              return { Component: ReportsListPage }
            },
          },
          {
            path: 'reports/:id',
            lazy: async () => {
              const { ReportDetailPage } = await import('@/features/reports/ReportDetailPage')
              return { Component: ReportDetailPage }
            },
          },
          {
            path: 'academy-report',
            lazy: async () => {
              const { AcademyReportsListPage } = await import('@/features/academyReport/AcademyReportsListPage')
              return { Component: AcademyReportsListPage }
            },
          },
          {
            path: 'academy-report/:id',
            lazy: async () => {
              const { AcademyReportDetailPage } = await import('@/features/academyReport/AcademyReportDetailPage')
              return { Component: AcademyReportDetailPage }
            },
          },
          {
            path: 'scholarships',
            lazy: async () => {
              const { ScholarshipsPage } = await import('@/features/scholarships/ScholarshipsPage')
              return { Component: ScholarshipsPage }
            },
          },
          {
            // «Моя зарплата» Тренера и Team Lead (backend: /accounting/my/salary/ — только свои, только чтение).
            element: <RequireRoles roles={['teacher', 'team_lead']} />,
            children: [
              {
                path: 'my-salary',
                lazy: async () => ({ Component: (await import('@/features/accounting/MySalaryPage')).MySalaryPage }),
              },
            ],
          },
          { path: 'salary', element: <Navigate to="/app/my-salary" replace /> },
          {
            path: 'news',
            lazy: async () => {
              const { NewsListPage } = await import('@/features/news/NewsListPage')
              return { Component: NewsListPage }
            },
          },
          {
            path: 'news/:id',
            lazy: async () => {
              const { NewsDetailPage } = await import('@/features/news/NewsDetailPage')
              return { Component: NewsDetailPage }
            },
          },
          {
            path: 'profile',
            lazy: async () => {
              const { ProfilePage } = await import('@/features/profile/ProfilePage')
              return { Component: ProfilePage }
            },
          },
        ],
      },
    ],
  },
  {
    // Assistant Workspace — daily academy operations (backend: apps.assistant,
    // IsAdminOrAssistant). Its own layout; never the Team Lead / Trainer pages.
    path: '/assistant',
    element: <ProtectedRoute />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <RequireRoles roles={['assistant', 'admin']} />,
        children: [
          {
            lazy: async () => {
              const { AssistantLayout } = await import('@/features/assistant/layout/AssistantLayout')
              return { Component: AssistantLayout }
            },
            children: [
              { index: true, lazy: async () => ({ Component: (await import('@/features/assistant/pages/DashboardPage')).AssistantDashboardPage }) },
              { path: 'groups', lazy: async () => ({ Component: (await import('@/features/assistant/pages/GroupsPage')).AssistantGroupsPage }) },
              { path: 'groups/create', lazy: async () => ({ Component: (await import('@/features/assistant/pages/GroupCreatePage')).AssistantGroupCreatePage }) },
              { path: 'groups/:id', lazy: async () => ({ Component: (await import('@/features/assistant/pages/GroupDetailPage')).AssistantGroupDetailPage }) },
              { path: 'students', lazy: async () => ({ Component: (await import('@/features/assistant/pages/StudentsPage')).AssistantStudentsPage }) },
              { path: 'students/create', lazy: async () => ({ Component: (await import('@/features/assistant/pages/StudentCreatePage')).AssistantStudentCreatePage }) },
              { path: 'students/:id', lazy: async () => ({ Component: (await import('@/features/assistant/pages/StudentDetailPage')).AssistantStudentDetailPage }) },
              { path: 'schedule', lazy: async () => ({ Component: (await import('@/features/assistant/pages/SchedulePage')).AssistantSchedulePage }) },
              { path: 'control', lazy: async () => ({ Component: (await import('@/features/assistant/pages/ControlPage')).AssistantControlPage }) },
              { path: 'reports', lazy: async () => ({ Component: (await import('@/features/assistant/pages/MonthlyReportPage')).AssistantMonthlyReportPage }) },
              { path: 'attendance', lazy: async () => ({ Component: (await import('@/features/assistant/pages/AttendancePage')).AssistantAttendancePage }) },
              { path: 'scholarships', lazy: async () => ({ Component: (await import('@/features/assistant/pages/ScholarshipsPage')).AssistantScholarshipsPage }) },
              { path: 'surveys', lazy: async () => ({ Component: (await import('@/features/assistant/pages/SurveysPage')).AssistantSurveysPage }) },
              { path: 'surveys/:id', lazy: async () => ({ Component: (await import('@/features/assistant/pages/SurveyDetailPage')).AssistantSurveyDetailPage }) },
              { path: 'my-salary', lazy: async () => ({ Component: (await import('@/features/accounting/MySalaryPage')).MySalaryPage }) },
              { path: 'profile', lazy: async () => ({ Component: (await import('@/features/assistant/pages/ProfilePage')).AssistantProfilePage }) },
              { path: '*', lazy: async () => ({ Component: (await import('@/features/assistant/pages/NotFoundPage')).AssistantNotFoundPage }) },
            ],
          },
        ],
      },
    ],
  },
  {
    // Бухгалтерия — Бухгалтер, Директор; Администратор только просматривает
    // (backend: apps.accounting.permissions). Свой layout, как у ассистента.
    path: '/accounting',
    element: <ProtectedRoute />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <RequireRoles roles={['accountant', 'director', 'admin']} />,
        children: [
          {
            lazy: async () => ({ Component: (await import('@/features/accounting/AccountingLayout')).AccountingLayout }),
            children: [
              { index: true, lazy: async () => ({ Component: (await import('@/features/accounting/DashboardPage')).AccountingDashboardPage }) },
              { path: 'payrolls/:id', lazy: async () => ({ Component: (await import('@/features/accounting/PayrollDetailPage')).PayrollDetailPage }) },
              { path: 'settings', lazy: async () => ({ Component: (await import('@/features/accounting/SalarySettingsPage')).SalarySettingsPage }) },
              { path: 'courses', lazy: async () => ({ Component: (await import('@/features/accounting/CoursesPage')).CoursesPage }) },
              { path: 'student-payments', lazy: async () => ({ Component: (await import('@/features/accounting/StudentPaymentsPage')).StudentPaymentsPage }) },
              { path: 'audit', lazy: async () => ({ Component: (await import('@/features/accounting/AuditPage')).AuditPage }) },
              { path: '*', element: <Navigate to="/accounting" replace /> },
            ],
          },
        ],
      },
    ],
  },
  {
    // «OkurmenKIDS Schedule» — the PUBLIC schedule site: no login, its own
    // layout, only the public read-only API (/api/v1/public/schedule/ —
    // whitelisted fields, no personal data). Never behind ProtectedRoute.
    path: '/schedule',
    errorElement: <RouteErrorPage />,
    lazy: async () => ({ Component: (await import('@/features/scheduleSite/SiteLayout')).SiteLayout }),
    children: [
      { index: true, lazy: async () => ({ Component: (await import('@/features/scheduleSite/SchedulePage')).ScheduleIndex }) },
      { path: 'day', lazy: async () => ({ Component: (await import('@/features/scheduleSite/SiteRoutes')).SiteDayPage }) },
      { path: 'week', lazy: async () => ({ Component: (await import('@/features/scheduleSite/SiteRoutes')).SiteWeekPage }) },
      { path: '*', element: <Navigate to="/schedule" replace /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
])

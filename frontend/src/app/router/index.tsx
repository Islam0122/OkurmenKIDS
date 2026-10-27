import { createBrowserRouter, Navigate } from 'react-router-dom'

import { AppLayout } from '@/app/layouts/AppLayout'
import { AccessDeniedPage } from '@/features/auth/AccessDeniedPage'
import { LoginPage } from '@/features/auth/LoginPage'
import { HOME_PATH } from '@/lib/appMode'
import { STAFF_ONLY_ROLES } from '@/lib/roles'

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
          // Главная бухгалтерии — четыре карточки разделов, без sidebar (вне AccountingLayout).
          { index: true, lazy: async () => ({ Component: (await import('@/features/accounting/HomePage')).AccountingHomePage }) },
          {
            lazy: async () => ({ Component: (await import('@/features/accounting/AccountingLayout')).AccountingLayout }),
            children: [
              { path: 'payroll', lazy: async () => ({ Component: (await import('@/features/accounting/DashboardPage')).AccountingDashboardPage }) },
              { path: 'expenses', lazy: async () => ({ Component: (await import('@/features/accounting/ExpensesPage')).ExpensesPage }) },
              { path: 'finance', lazy: async () => ({ Component: (await import('@/features/accounting/FinancePanelPage')).FinancePanelPage }) },
              { path: 'cash', lazy: async () => ({ Component: (await import('@/features/accounting/CashFlowPage')).CashFlowPage }) },
              { path: 'payrolls/:id', lazy: async () => ({ Component: (await import('@/features/accounting/PayrollDetailPage')).PayrollDetailPage }) },
              { path: 'earnings', lazy: async () => ({ Component: (await import('@/features/accounting/EarningsPage')).EarningsPage }) },
              { path: 'payout-plan', lazy: async () => ({ Component: (await import('@/features/accounting/PayoutPlanPage')).PayoutPlanPage }) },
              { path: 'payout-plan/:id', lazy: async () => ({ Component: (await import('@/features/accounting/PayoutPlanDetailPage')).PayoutPlanDetailPage }) },
              { path: 'settings', lazy: async () => ({ Component: (await import('@/features/accounting/SalarySettingsPage')).SalarySettingsPage }) },
              { path: 'courses', lazy: async () => ({ Component: (await import('@/features/accounting/CoursesPage')).CoursesPage }) },
              { path: 'billing', element: <Navigate to="/finance" replace /> },
              { path: 'student-payments', lazy: async () => ({ Component: (await import('@/features/accounting/StudentPaymentsPage')).StudentPaymentsPage }) },
              { path: 'audit', lazy: async () => ({ Component: (await import('@/features/accounting/AuditPage')).AuditPage }) },
              { path: 'pricing', lazy: async () => ({ Component: (await import('@/features/accounting/PricingPage')).PricingPage }) },
              { path: 'analytics', lazy: async () => ({ Component: (await import('@/features/accounting/AnalyticsPage')).AnalyticsPage }) },
              { path: 'reports', lazy: async () => ({ Component: (await import('@/features/accounting/ReportsPage')).ReportsPage }) },
              { path: '*', element: <Navigate to="/accounting" replace /> },
            ],
          },
        ],
      },
    ],
  },
  {
    // Финансы студентов: договоры по программам, учебные месяцы, оплаты, чеки
    // (backend: apps.billing). Бухгалтер — всё; Директор — только просмотр;
    // Менеджер (ассистент) — договоры и статусы. Права проверяет backend.
    path: '/finance',
    element: <ProtectedRoute />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <RequireRoles roles={['accountant', 'director', 'admin', 'assistant']} />,
        children: [
          {
            lazy: async () => ({ Component: (await import('@/features/finance/FinanceLayout')).FinanceLayout }),
            children: [
              { index: true, lazy: async () => ({ Component: (await import('@/features/finance/DashboardPage')).FinanceDashboardPage }) },
              { path: 'to-pay', lazy: async () => ({ Component: (await import('@/features/finance/QueuePage')).ToPayPage }) },
              { path: 'soon', lazy: async () => ({ Component: (await import('@/features/finance/SoonPage')).SoonPage }) },
              { path: 'overdue', lazy: async () => ({ Component: (await import('@/features/finance/QueuePage')).OverduePage }) },
              { path: 'students', lazy: async () => ({ Component: (await import('@/features/finance/StudentsPage')).StudentsPage }) },
              { path: 'students/:profileId', lazy: async () => ({ Component: (await import('@/features/finance/StudentCardPage')).StudentCardPage }) },
              { path: 'contracts/new', lazy: async () => ({ Component: (await import('@/features/finance/NewContractPage')).NewContractPage }) },
              { path: 'payments', lazy: async () => ({ Component: (await import('@/features/finance/PaymentsPage')).PaymentsPage }) },
              { path: 'payments/new', lazy: async () => ({ Component: (await import('@/features/finance/AddPaymentPage')).AddPaymentPage }) },
              { path: 'prepayments', lazy: async () => ({ Component: (await import('@/features/finance/PrepaymentsPage')).PrepaymentsPage }) },
              { path: 'payments/:paymentId', lazy: async () => ({ Component: (await import('@/features/finance/PaymentDetailPage')).PaymentDetailPage }) },
              { path: 'receipts', lazy: async () => ({ Component: (await import('@/features/finance/ReceiptPage')).ReceiptsPage }) },
              { path: 'receipts/:receiptId', lazy: async () => ({ Component: (await import('@/features/finance/ReceiptPage')).ReceiptPage }) },
              { path: 'analytics', lazy: async () => ({ Component: (await import('@/features/finance/AnalyticsPage')).AnalyticsPage }) },
              { path: 'plans', lazy: async () => ({ Component: (await import('@/features/finance/AdminPages')).PlansPage }) },
              { path: 'audit', lazy: async () => ({ Component: (await import('@/features/finance/AdminPages')).AuditPage }) },
              { path: 'settings', lazy: async () => ({ Component: (await import('@/features/finance/AdminPages')).SettingsPage }) },
              { path: '*', element: <Navigate to="/finance" replace /> },
            ],
          },
        ],
      },
    ],
  },
  {
    // Учёт прихода и ухода сотрудников по QR-коду офиса (backend:
    // apps.staff_attendance). Личная страница — у каждой категории своя;
    // /attendance/scan — куда ведёт QR, отсканированный камерой телефона.
    path: '/attendance',
    element: <ProtectedRoute />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        lazy: async () => ({ Component: (await import('@/features/staffAttendance/AttendanceLayout')).AttendanceLayout }),
        children: [
          { index: true, lazy: async () => ({ Component: (await import('@/features/staffAttendance/pages')).AttendanceHomeRedirect }) },
          { path: 'scan', lazy: async () => ({ Component: (await import('@/features/staffAttendance/pages')).ScanLandingPage }) },
          {
            element: <RequireRoles roles={['teacher']} redirectTo="/attendance" />,
            children: [{ path: 'teacher', lazy: async () => ({ Component: (await import('@/features/staffAttendance/pages')).TeacherAttendancePage }) }],
          },
          {
            element: <RequireRoles roles={['accountant']} redirectTo="/attendance" />,
            children: [{ path: 'accounting', lazy: async () => ({ Component: (await import('@/features/staffAttendance/pages')).AccountingAttendancePage }) }],
          },
          {
            element: <RequireRoles roles={['assistant']} redirectTo="/attendance" />,
            children: [{ path: 'assistant', lazy: async () => ({ Component: (await import('@/features/staffAttendance/pages')).AssistantAttendancePage }) }],
          },
          {
            element: <RequireRoles roles={['admin', 'director', 'team_lead']} redirectTo="/attendance" />,
            children: [{ path: 'office', lazy: async () => ({ Component: (await import('@/features/staffAttendance/pages')).OfficeAttendancePage }) }],
          },
          {
            // ДОП, РОП, РОМ, операционный директор, HR, продажи, маркетинг.
            element: <RequireRoles roles={STAFF_ONLY_ROLES} redirectTo="/attendance" />,
            children: [{ path: 'staff', lazy: async () => ({ Component: (await import('@/features/staffAttendance/pages')).StaffAttendancePage }) }],
          },
          // Отчёты руководства/HR: доступ решает backend (admin/meta → 403 → назад в кабинет).
          { path: 'management', lazy: async () => ({ Component: (await import('@/features/staffAttendance/AdminAttendancePage')).ManagementAttendancePage }) },
          { path: '*', element: <Navigate to="/attendance" replace /> },
        ],
      },
    ],
  },
  {
    // HR-кабинет: главная, сотрудники, кандидаты, собеседования, вакансии,
    // отчёты, своя зарплата (backend: apps.users.hr, apps.recruitment — только HR-менеджер).
    path: '/hr',
    element: <ProtectedRoute />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <RequireRoles roles={['hr_manager']} redirectTo="/attendance" />,
        children: [
          {
            lazy: async () => ({ Component: (await import('@/features/hr/HrLayout')).HrLayout }),
            children: [
              { index: true, lazy: async () => ({ Component: (await import('@/features/hr/DashboardPage')).HrDashboardPage }) },
              { path: 'employees', lazy: async () => ({ Component: (await import('@/features/hr/EmployeesPage')).HrEmployeesPage }) },
              { path: 'employees/:id', lazy: async () => ({ Component: (await import('@/features/hr/EmployeeCardPage')).HrEmployeeCardPage }) },
              { path: 'candidates', lazy: async () => ({ Component: (await import('@/features/hr/CandidatesPage')).HrCandidatesPage }) },
              { path: 'candidates/:id', lazy: async () => ({ Component: (await import('@/features/hr/CandidateCardPage')).HrCandidateCardPage }) },
              { path: 'interviews', lazy: async () => ({ Component: (await import('@/features/hr/InterviewsPage')).HrInterviewsPage }) },
              { path: 'vacancies', lazy: async () => ({ Component: (await import('@/features/hr/VacanciesPage')).HrVacanciesPage }) },
              { path: 'vacancies/new', lazy: async () => ({ Component: (await import('@/features/hr/VacancyEditPage')).HrVacancyEditPage }) },
              { path: 'vacancies/:id', lazy: async () => ({ Component: (await import('@/features/hr/VacancyEditPage')).HrVacancyEditPage }) },
              { path: 'reports', lazy: async () => ({ Component: (await import('@/features/hr/ReportsPage')).HrReportsPage }) },
              // Своя зарплата HR — та же страница и тот же API, что у тренеров (/accounting/my/salary/).
              { path: 'my-salary', lazy: async () => ({ Component: (await import('@/features/accounting/MySalaryPage')).MySalaryPage }) },
              { path: '*', element: <Navigate to="/hr" replace /> },
            ],
          },
        ],
      },
    ],
  },
  {
    // Центральная панель учёта посещаемости, офисы с QR-кодами и настройки.
    // Права (отчёты / исправления / управление) — с backend, см. admin/meta.
    path: '/admin/attendance',
    element: <ProtectedRoute />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        lazy: async () => ({ Component: (await import('@/features/staffAttendance/AttendanceLayout')).AttendanceLayout }),
        children: [
          { index: true, lazy: async () => ({ Component: (await import('@/features/staffAttendance/AdminAttendancePage')).AdminAttendancePage }) },
          { path: 'locations', lazy: async () => ({ Component: (await import('@/features/staffAttendance/LocationsPage')).LocationsPage }) },
          { path: 'settings', lazy: async () => ({ Component: (await import('@/features/staffAttendance/SettingsPage')).SettingsPage }) },
          { path: '*', element: <Navigate to="/admin/attendance" replace /> },
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
  {
    // «OkurmenKIDS Leaderboard» — the PUBLIC leaderboard site: no login, its
    // own layout, only the public read-only API (/api/v1/public/leaderboard/ —
    // public names, opaque keys and XP; no personal data). Never behind
    // ProtectedRoute.
    path: '/leaderboard',
    errorElement: <RouteErrorPage />,
    lazy: async () => ({ Component: (await import('@/features/leaderboardSite/SiteLayout')).SiteLayout }),
    children: [
      { index: true, lazy: async () => ({ Component: (await import('@/features/leaderboardSite/LeaderboardPages')).StudentsLeaderboardPage }) },
      { path: 'groups', lazy: async () => ({ Component: (await import('@/features/leaderboardSite/LeaderboardPages')).GroupsLeaderboardPage }) },
      { path: '*', element: <Navigate to="/leaderboard" replace /> },
    ],
  },
  {
    // Карьерный сайт — ПУБЛИЧНЫЙ: без входа, свой layout, только публичный API
    // вакансий (/api/v1/public/careers/ — белый список полей, без внутренних
    // данных). Отклик — без регистрации. Никогда не за ProtectedRoute.
    path: '/careers',
    errorElement: <RouteErrorPage />,
    lazy: async () => ({ Component: (await import('@/features/careers/SiteLayout')).CareersLayout }),
    children: [
      { index: true, lazy: async () => ({ Component: (await import('@/features/careers/CareersHomePage')).CareersHomePage }) },
      { path: 'vacancies/:slug', lazy: async () => ({ Component: (await import('@/features/careers/VacancyPage')).VacancyPage }) },
      { path: 'privacy', lazy: async () => ({ Component: (await import('@/features/careers/PrivacyPage')).CareersPrivacyPage }) },
      { path: '*', element: <Navigate to="/careers" replace /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
])

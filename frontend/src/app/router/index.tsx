import { createBrowserRouter, Navigate } from 'react-router-dom'

import { AppLayout } from '@/app/layouts/AppLayout'
import { AccessDeniedPage } from '@/features/auth/AccessDeniedPage'
import { LoginPage } from '@/features/auth/LoginPage'

import { NotFoundPage } from './NotFoundPage'
import { ProtectedRoute } from './ProtectedRoute'

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/app/dashboard" replace /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/access-denied', element: <AccessDeniedPage /> },
  {
    path: '/app',
    element: <ProtectedRoute />,
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
  { path: '*', element: <NotFoundPage /> },
])

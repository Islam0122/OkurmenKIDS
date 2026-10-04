import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { ExamLayout } from '@/layouts/ExamLayout'
import { ExamAttemptPage } from '@/pages/ExamAttemptPage'
import { ExamResultPage } from '@/pages/ExamResultPage'
import { MainLayout } from '@/layouts/MainLayout'
import { PortalProvider } from '@/context/PortalContext'
import { ExamPage } from '@/pages/ExamPage'
import { HomePage } from '@/pages/HomePage'
import { LeaderboardPage } from '@/pages/LeaderboardPage'
import { MaterialsPage } from '@/pages/MaterialsPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { ResultPage } from '@/pages/ResultPage'
import { TrainingListPage } from '@/pages/TrainingListPage'
import { TrainingPage } from '@/pages/TrainingPage'
import { VideosPage } from '@/pages/VideosPage'

export function AppRoutes() {
  return (
    <PortalProvider>
    <Routes>
      {/* The test itself: ExamLayout — no site navigation. */}
      <Route element={<ExamLayout />}>
        <Route path="training/:testId" element={<TrainingPage />} />
        {/* The exam runs on the same test screen (attempt from the student portal). */}
        <Route path="exam/:attemptId" element={<ExamAttemptPage />} />
        <Route path="exam/:attemptId/result" element={<ExamResultPage />} />
      </Route>
      <Route element={<MainLayout />}>
        <Route index element={<HomePage />} />
        <Route path="training" element={<TrainingListPage />} />
        <Route path="result/:attemptId" element={<ResultPage />} />
        <Route path="leaderboard" element={<LeaderboardPage />} />
        <Route path="videos" element={<VideosPage />} />
        <Route path="materials" element={<MaterialsPage />} />
        <Route path="exam" element={<ExamPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
    </PortalProvider>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}

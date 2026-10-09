import { useContext, useState } from 'react'

import { LessonModal } from '@/features/assistant/actions/LessonModal'
import { ScheduleModal } from '@/features/assistant/actions/ScheduleModal'
import { AuthContext } from '@/features/auth/AuthContext'
import { LessonPreviewModal } from '@/features/scheduleBoard/LessonPreviewModal'
import { ScheduleBoard } from '@/features/scheduleBoard/ScheduleBoard'
import type { AddLessonPreset } from '@/features/scheduleBoard/ScheduleBoard'
import type { BoardLesson } from '@/types/schedule'

import { TrainerSchedule } from './TrainerSchedule'

/**
 * /app/schedule. A Trainer sees their own lessons (TrainerSchedule); Admin
 * and Team Lead get the academy-wide schedule board — the same component
 * and API as the Assistant's page. What a click may do comes from the
 * backend (`can_edit`): Admin moves / cancels / adds, a Team Lead reads.
 */
export function SchedulePage() {
  const role = useContext(AuthContext)?.user?.role
  if (role === 'team_lead' || role === 'admin') return <AcademySchedule />
  return <TrainerSchedule />
}

function AcademySchedule() {
  const [opened, setOpened] = useState<{ lesson: BoardLesson; canEdit: boolean } | null>(null)
  const [adding, setAdding] = useState<{ preset?: AddLessonPreset } | null>(null)
  return (
    <>
      <ScheduleBoard
        storageKey="okurmen.schedule.academy"
        description="Все занятия академии с 08:00 до 24:00: тренеры, кабинеты, группы и пересечения."
        onOpenLesson={(lesson, canEdit) => setOpened({ lesson, canEdit })}
        onAddLesson={(preset) => setAdding({ preset })}
      />
      {opened?.canEdit ? <LessonModal lesson={opened.lesson} onClose={() => setOpened(null)} /> : null}
      {opened && !opened.canEdit ? <LessonPreviewModal lesson={opened.lesson} detailsHref={`/app/lessons/${opened.lesson.id}`} onClose={() => setOpened(null)} /> : null}
      {adding ? (
        <ScheduleModal
          preset={adding.preset ? { day: adding.preset.day, start: adding.preset.start, end: adding.preset.end, room: adding.preset.room } : undefined}
          onClose={() => setAdding(null)}
        />
      ) : null}
    </>
  )
}

import { ScheduleBoard } from '@/features/scheduleBoard/ScheduleBoard'

import { useAssistantActions } from '../actions/AssistantActions'

/**
 * Assistant → «Расписание»: the shared schedule board (the same one the Team
 * Lead uses). A lesson opens the Assistant's lesson modal — move with the
 * conflict check, cancel with confirmation; «Добавить занятие» (or a click
 * on a free spot) adds a weekly slot to a group's program.
 */
export function AssistantSchedulePage() {
  const { open } = useAssistantActions()
  return (
    <ScheduleBoard
      storageKey="okurmen.schedule.assistant"
      description="Занятия всех групп с 08:00 до 24:00. Нажмите на занятие — перенос, отмена, посещаемость."
      onOpenLesson={(lesson) => open({ type: 'lesson', lesson })}
      onAddLesson={(preset) => open({ type: 'schedule', preset: preset ? { day: preset.day, start: preset.start, end: preset.end, room: preset.room } : undefined })}
    />
  )
}

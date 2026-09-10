import { LessonCard } from '@/components/academy/LessonCard'
import { EmptyState } from '@/components/ui/EmptyState'
import type { Lesson } from '@/types/academy'

export interface DayScheduleProps {
  date: string
  lessons: Lesson[]
}

export function DaySchedule({ lessons }: DayScheduleProps) {
  if (lessons.length === 0) {
    return <EmptyState title="На этот день занятий нет" />
  }

  return (
    <div className="space-y-3">
      {lessons.map((lesson) => (
        <LessonCard key={lesson.id} lesson={lesson} />
      ))}
    </div>
  )
}

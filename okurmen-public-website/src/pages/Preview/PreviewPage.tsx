import { Eye } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { ErrorState, NotFoundState, PageSkeleton } from '@/components/shared/States'
import { isNotFound, usePreview } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import { AchievementView } from '@/pages/Achievements/AchievementDetailPage'
import { CourseView } from '@/pages/Courses/CourseDetailPage'
import { EventView } from '@/pages/Events/EventDetailPage'
import { ArticleView } from '@/pages/News/ArticlePage'

/** /preview/<signed token> — a draft opened from the LMS editor «Предпросмотр». Never indexed. */
export function PreviewPage() {
  const { token = '' } = useParams()
  const { t } = useI18n()
  const { data, isPending, isError, error, refetch } = usePreview(token)
  if (isPending) return <PageSkeleton />
  if (isError) return isNotFound(error) ? <NotFoundState /> : <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>
  return (
    <>
      <div role="note" className="sticky top-[72px] z-30 flex items-center justify-center gap-2 bg-brand-800 px-4 py-2.5 text-center text-sm font-bold text-white lg:top-20">
        <Eye className="size-4 text-gold-400" aria-hidden /> {t('state.preview')}
      </div>
      {data.kind === 'course' ? <CourseView course={data.item} preview /> : null}
      {data.kind === 'event' ? <EventView event={data.item} preview /> : null}
      {data.kind === 'achievement' ? <AchievementView item={data.item} preview /> : null}
      {data.kind === 'news' ? <ArticleView article={data.item} preview /> : null}
    </>
  )
}

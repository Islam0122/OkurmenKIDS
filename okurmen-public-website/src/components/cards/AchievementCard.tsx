import { Award, Images } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/shared/Badge'
import { SmartImage } from '@/components/shared/SmartImage'
import { useI18n } from '@/i18n'
import type { AchievementCard as Achievement } from '@/types/api'

export function AchievementCard({ item }: { item: Achievement }) {
  const { t, path, formatDate } = useI18n()
  return (
    <Link to={path(`/achievements/${item.slug}`)} className="card card-hover group flex h-full flex-col overflow-hidden">
      <div className="relative aspect-[4/3] overflow-hidden bg-gradient-to-br from-gold-100 to-brand-50">
        <SmartImage image={item.cover} alt={item.title} className="size-full transition duration-700 group-hover:scale-105" fallback={<Award className="size-14 text-gold-500" strokeWidth={1.5} aria-hidden />} />
        <Badge tone="white" className="absolute top-4 left-4">{t(`achievements.cat.${item.category}`)}</Badge>
      </div>
      <div className="flex flex-1 flex-col p-6">
        <time dateTime={item.date} className="text-sm font-semibold text-gold-600">{formatDate(item.date)}</time>
        <h3 className="mt-2 text-lg leading-snug font-extrabold">{item.title}</h3>
        {item.excerpt ? <p className="mt-2 line-clamp-3 text-[15px] text-muted">{item.excerpt}</p> : null}
        {item.photo_count > 1 ? (
          <span className="mt-auto flex items-center gap-1.5 pt-4 text-xs font-semibold text-muted"><Images className="size-4" aria-hidden />{item.photo_count}</span>
        ) : null}
      </div>
    </Link>
  )
}

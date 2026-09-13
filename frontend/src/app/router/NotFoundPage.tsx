import { CompassIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import { FullScreenStatus } from '@/components/ui/FullScreenStatus'

export function NotFoundPage() {
  return (
    <FullScreenStatus
      icon={CompassIcon}
      title="Страница не найдена"
      description="Похоже, такого раздела не существует."
      actions={
        <Link
          to="/app/dashboard"
          className="inline-flex h-10 items-center justify-center rounded-lg bg-brand-500 px-4 text-sm font-medium text-white hover:bg-brand-600"
        >
          На главную
        </Link>
      }
    />
  )
}

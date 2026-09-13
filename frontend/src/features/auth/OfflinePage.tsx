import { WifiOff } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { FullScreenStatus } from '@/components/ui/FullScreenStatus'

export interface OfflinePageProps {
  onRetry: () => void
}

/** Shown when the app can't reach the backend at all (down, or the network dropped) — deliberately distinct from "guest": we never throw away a possibly-valid session over a connectivity blip. */
export function OfflinePage({ onRetry }: OfflinePageProps) {
  return (
    <FullScreenStatus
      icon={WifiOff}
      tone="warning"
      title="Сервер недоступен"
      description="Не удалось связаться с сервером OkurmenKIDS. Проверьте подключение к интернету и попробуйте ещё раз."
      actions={
        <Button variant="secondary" onClick={onRetry}>
          Попробовать снова
        </Button>
      }
    />
  )
}

import { ApiError, CONFIG_ERROR, NETWORK_ERROR } from '@/api/client'
import { t } from '@/i18n'

import { Button } from '../Button'
import { Icon } from '../Icon'

export function errorText(error: ApiError | null | undefined): string {
  if (!error) return ''
  if (error.code === NETWORK_ERROR) return t.errors.network
  if (error.code === CONFIG_ERROR) return t.errors.config
  return error.message
}

export function ErrorState({ error, onRetry, title = t.errors.title }: { error: ApiError | null; onRetry?: () => void; title?: string }) {
  return (
    <div className="empty" role="alert" style={{ margin: '24px 0' }}>
      <Icon name="cloud-slash" />
      <h2 className="section-title" style={{ fontSize: 22, marginBottom: 8 }}>{title}</h2>
      <p>{errorText(error)}</p>
      {onRetry ? <div style={{ marginTop: 20 }}><Button variant="outline" icon="arrow-clockwise" onClick={onRetry}>{t.errors.retry}</Button></div> : null}
    </div>
  )
}

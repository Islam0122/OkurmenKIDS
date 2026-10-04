import { Button } from '@/components/Button'
import { Icon } from '@/components/Icon'
import { t } from '@/i18n'

export function NotFoundPage({ title = t.common.notFound }: { title?: string }) {
  return (
    <div className="container" style={{ padding: '96px 16px' }}>
      <div className="empty" style={{ maxWidth: 520, margin: '0 auto' }}>
        <Icon name="compass" />
        <h1 className="section-title" style={{ marginBottom: 8 }}>{title}</h1>
        <p>{t.common.notFoundText}</p>
        <div style={{ marginTop: 24 }}><Button to="/" icon="house">{t.common.home}</Button></div>
      </div>
    </div>
  )
}

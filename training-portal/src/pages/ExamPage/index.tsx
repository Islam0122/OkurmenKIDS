import { useEffect } from 'react'

import { Button } from '@/components/Button'
import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { usePortal } from '@/context/PortalContext'
import { t } from '@/i18n'

/** /exam — hands the student over to the real exam (URL set in the backend). */
export function ExamPage() {
  const { data: portal, loading } = usePortal()

  useEffect(() => {
    if (!portal?.exam_url) return
    if (portal.exam_open_in_new_tab) window.open(portal.exam_url, '_blank', 'noopener,noreferrer')
    else window.location.href = portal.exam_url
  }, [portal])

  if (loading) return <Loader />
  return (
    <div className="container" style={{ padding: '80px 16px' }}>
      <div className="empty" style={{ maxWidth: 560, margin: '0 auto' }}>
        <Icon name="mortarboard" />
        <h1 className="section-title" style={{ marginBottom: 8 }}>{portal?.exam_url ? t.exam.redirecting : t.exam.unavailable}</h1>
        <p>{portal?.exam_url ? t.exam.text : t.exam.unavailableText}</p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap', marginTop: 24 }}>
          {portal?.exam_url ? (
            <Button href={portal.exam_url} newTab={portal.exam_open_in_new_tab} variant="navy" iconEnd="box-arrow-up-right">{t.exam.open}</Button>
          ) : null}
          <Button to="/" variant="outline" icon="house">{t.exam.back}</Button>
        </div>
      </div>
    </div>
  )
}

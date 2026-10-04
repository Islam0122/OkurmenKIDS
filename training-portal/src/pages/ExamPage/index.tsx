import { useEffect } from 'react'

import { Button } from '@/components/Button'
import { Icon } from '@/components/Icon'
import { siteConfig } from '@/config/site'
import { t } from '@/i18n'

/** /exam — hands the student over to the real exam in the LMS. */
export function ExamPage() {
  useEffect(() => {
    if (siteConfig.openInNewTab) window.open(siteConfig.examUrl, '_blank', 'noopener,noreferrer')
    else window.location.href = siteConfig.examUrl
  }, [])

  return (
    <div className="container" style={{ padding: '80px 16px' }}>
      <div className="empty" style={{ maxWidth: 560, margin: '0 auto' }}>
        <Icon name="mortarboard" />
        <h1 className="section-title" style={{ marginBottom: 8 }}>{t.exam.redirecting}</h1>
        <p>{t.exam.text}</p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap', marginTop: 24 }}>
          <Button href={siteConfig.examUrl} newTab={siteConfig.openInNewTab} variant="navy" iconEnd="box-arrow-up-right">{t.exam.open}</Button>
          <Button to="/" variant="outline" icon="house">{t.exam.back}</Button>
        </div>
      </div>
    </div>
  )
}

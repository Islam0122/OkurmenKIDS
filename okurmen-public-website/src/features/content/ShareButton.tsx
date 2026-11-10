import { Check, Share2 } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/i18n'

export function ShareButton({ title }: { title: string }) {
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  const share = async () => {
    const url = window.location.href
    try {
      if (navigator.share) {
        await navigator.share({ title, url })
        return
      }
      await navigator.clipboard.writeText(url)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      /* cancelled */
    }
  }
  return (
    <Button variant="outline" size="sm" onClick={share} aria-live="polite">
      {copied ? <Check className="size-4" aria-hidden /> : <Share2 className="size-4" aria-hidden />}
      {copied ? t('cta.copied') : t('cta.share')}
    </Button>
  )
}

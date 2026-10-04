import { siteConfig } from '@/config/site'
import { t } from '@/i18n'

import { Button, type ButtonVariant } from '.'

/**
 * «Экзаменге өтүү» — opens the real exam in the LMS (siteConfig.examUrl).
 * It never starts a training attempt: training and the exam are separate.
 */
export function ExamButton({ variant = 'navy', size, block, label = t.nav.exam }: {
  variant?: ButtonVariant
  size?: 'sm' | 'md' | 'lg'
  block?: boolean
  label?: string
}) {
  return (
    <Button
      href={siteConfig.examUrl}
      newTab={siteConfig.openInNewTab}
      variant={variant}
      size={size}
      block={block}
      icon="mortarboard"
      iconEnd={siteConfig.openInNewTab ? 'box-arrow-up-right' : 'arrow-right'}
    >
      {label}
    </Button>
  )
}

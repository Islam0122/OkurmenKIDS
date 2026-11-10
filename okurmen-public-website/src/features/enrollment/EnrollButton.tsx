import { ArrowRight } from 'lucide-react'

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/i18n'

import { useEnroll } from './EnrollmentProvider'

/** The main call to action, available everywhere. */
export function EnrollButton({ course, size = 'md', variant = 'primary', className, label }: { course?: string; size?: 'sm' | 'md' | 'lg'; variant?: 'primary' | 'secondary' | 'light' | 'outline'; className?: string; label?: string }) {
  const { t } = useI18n()
  const { openEnroll } = useEnroll()
  return (
    <Button size={size} variant={variant} className={className} onClick={() => openEnroll(course)}>
      {label ?? t('cta.enroll')}
      <ArrowRight className="size-4" aria-hidden />
    </Button>
  )
}

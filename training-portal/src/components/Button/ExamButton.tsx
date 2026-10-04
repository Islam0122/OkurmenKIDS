import { usePortal } from '@/context/PortalContext'

import { Button, type ButtonVariant } from '.'

/**
 * «Экзаменге өтүү» — opens the real exam: the URL the administrator set in
 * the backend (portal settings). Hidden while it isn't set. It never starts
 * a training attempt: training and the exam are separate systems.
 */
export function ExamButton({ variant = 'navy', size, block, label, url }: {
  variant?: ButtonVariant
  size?: 'sm' | 'md' | 'lg'
  block?: boolean
  label?: string
  /** a trainer's own exam link (from the API); else the portal's */
  url?: string
}) {
  const { data: portal } = usePortal()
  const href = url || portal?.exam_url
  if (!portal || !href) return null
  return (
    <Button
      href={href}
      newTab={portal.exam_open_in_new_tab}
      variant={variant}
      size={size}
      block={block}
      icon="mortarboard"
      iconEnd={portal.exam_open_in_new_tab ? 'box-arrow-up-right' : 'arrow-right'}
    >
      {label ?? portal.exam_button_label}
    </Button>
  )
}

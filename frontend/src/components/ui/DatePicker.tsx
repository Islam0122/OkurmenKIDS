import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'

import { cn } from '@/utils/cn'

export type DatePickerProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>

/**
 * A styled native `<input type="date">`. Deliberately not a custom calendar
 * widget — the native picker is already accessible and, on a phone, it's the
 * one-handed, thumb-friendly control a teacher expects; a hand-rolled one
 * would only make mobile worse.
 */
export const DatePicker = forwardRef<HTMLInputElement, DatePickerProps>(function DatePicker(
  { className, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      type="date"
      className={cn(
        'form-control',
        className,
      )}
      {...rest}
    />
  )
})

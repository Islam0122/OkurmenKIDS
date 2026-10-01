import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'

import { cn } from '@/utils/cn'

export type InputProps = InputHTMLAttributes<HTMLInputElement>

/** The shared text/number/time input — same 40px height and styling as Select, DatePicker and SearchInput. */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input({ className, type = 'text', ...rest }, ref) {
  return <input ref={ref} type={type} className={cn('form-control', className)} {...rest} />
})

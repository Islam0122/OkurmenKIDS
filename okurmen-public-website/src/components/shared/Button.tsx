import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { useI18n } from '@/i18n'
import { cn } from '@/utils/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'light' | 'outline'
type Size = 'sm' | 'md' | 'lg'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-gold-400 text-brand-900 shadow-gold hover:bg-gold-300 active:bg-gold-500',
  secondary: 'bg-brand-800 text-white hover:bg-brand-700 active:bg-brand-900',
  outline: 'border-2 border-brand-800/15 bg-white text-brand-800 hover:border-brand-800/40 hover:bg-brand-50',
  ghost: 'text-brand-800 hover:bg-brand-50',
  light: 'bg-white/10 text-white ring-1 ring-white/25 hover:bg-white/20 backdrop-blur',
}

const SIZES: Record<Size, string> = {
  sm: 'h-10 px-4 text-sm gap-1.5',
  md: 'h-12 px-6 text-[15px] gap-2',
  lg: 'h-14 px-7 text-base gap-2.5',
}

export function buttonClass(variant: Variant = 'primary', size: Size = 'md', className?: string) {
  return cn(
    'inline-flex shrink-0 items-center justify-center rounded-full font-bold whitespace-nowrap transition duration-200 select-none',
    'disabled:pointer-events-none disabled:opacity-60 active:scale-[0.98]',
    VARIANTS[variant],
    SIZES[size],
    className,
  )
}

interface CommonProps {
  variant?: Variant
  size?: Size
  className?: string
  children: ReactNode
}

export const Button = forwardRef<HTMLButtonElement, CommonProps & ButtonHTMLAttributes<HTMLButtonElement>>(
  function Button({ variant, size, className, children, type = 'button', ...rest }, ref) {
    return (
      <button ref={ref} type={type} className={buttonClass(variant, size, className)} {...rest}>
        {children}
      </button>
    )
  },
)

/** An internal link (localized automatically) or an external URL styled as a button. */
export function ButtonLink({ to, variant, size, className, children, ...rest }: CommonProps & { to: string; 'aria-label'?: string }) {
  const { path } = useI18n()
  if (/^(https?:|mailto:|tel:)/.test(to)) {
    const external = to.startsWith('http')
    return (
      <a href={to} className={buttonClass(variant, size, className)} {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})} {...rest}>
        {children}
      </a>
    )
  }
  return (
    <Link to={path(to)} className={buttonClass(variant, size, className)} {...rest}>
      {children}
    </Link>
  )
}

import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { Icon } from '../Icon'
import './Button.css'

export type ButtonVariant = 'primary' | 'navy' | 'outline' | 'ghost' | 'danger' | 'glass' | 'success'
type Size = 'sm' | 'md' | 'lg'

interface Common {
  variant?: ButtonVariant
  size?: Size
  block?: boolean
  icon?: string
  iconEnd?: string
  children: ReactNode
  className?: string
}

type Props =
  | (Common & { to: string; href?: never } )
  | (Common & { href: string; to?: never; newTab?: boolean })
  | (Common & { to?: never; href?: never } & ButtonHTMLAttributes<HTMLButtonElement>)

function classes({ variant = 'primary', size = 'md', block, className }: Common) {
  return ['btn', `btn--${variant}`, size !== 'md' && `btn--${size}`, block && 'btn--block', className].filter(Boolean).join(' ')
}

export function Button(props: Props) {
  const { icon, iconEnd, children } = props
  const content = (
    <>
      {icon ? <Icon name={icon} /> : null}
      <span>{children}</span>
      {iconEnd ? <Icon name={iconEnd} /> : null}
    </>
  )
  if ('to' in props && props.to) {
    return <Link to={props.to} className={classes(props)}>{content}</Link>
  }
  if ('href' in props && props.href) {
    const newTab = 'newTab' in props && props.newTab
    return (
      <a href={props.href} className={classes(props)} {...(newTab ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>
        {content}
      </a>
    )
  }
  const { variant: _v, size: _s, block: _b, icon: _i, iconEnd: _e, className: _c, children: _ch, type = 'button', ...rest } =
    props as Common & ButtonHTMLAttributes<HTMLButtonElement>
  return <button type={type} className={classes(props)} {...rest}>{content}</button>
}

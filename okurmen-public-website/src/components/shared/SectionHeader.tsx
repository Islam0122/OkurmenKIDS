import { ArrowRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { useI18n } from '@/i18n'
import { cn } from '@/utils/cn'

import { Reveal } from './Reveal'

interface Props {
  eyebrow?: ReactNode
  title: ReactNode
  text?: ReactNode
  link?: { to: string; label: string }
  align?: 'left' | 'center'
  className?: string
  as?: 'h1' | 'h2'
}

export function SectionHeader({ eyebrow, title, text, link, align = 'left', className, as: Heading = 'h2' }: Props) {
  const { path } = useI18n()
  return (
    <Reveal className={cn('mb-10 flex flex-col gap-5 sm:mb-12', align === 'center' ? 'items-center text-center' : 'md:flex-row md:items-end md:justify-between', className)}>
      <div className={cn('max-w-2xl', align === 'center' && 'mx-auto')}>
        {eyebrow ? <span className="eyebrow mb-4">{eyebrow}</span> : null}
        <Heading className="text-3xl leading-[1.1] font-extrabold sm:text-4xl lg:text-[2.75rem]">{title}</Heading>
        {text ? <p className="mt-4 text-base text-muted sm:text-lg">{text}</p> : null}
      </div>
      {link ? (
        <Link to={path(link.to)} className="group inline-flex shrink-0 items-center gap-2 font-bold text-brand-700 hover:text-brand-900">
          {link.label}
          <ArrowRight className="size-4 transition group-hover:translate-x-1" aria-hidden />
        </Link>
      ) : null}
    </Reveal>
  )
}

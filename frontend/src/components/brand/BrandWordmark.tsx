import { BRAND } from '@/lib/brand'
import { cn } from '@/utils/cn'

interface BrandWordmarkProps {
  /** Show «ОБРАЗОВАТЕЛЬНАЯ ЭКОСИСТЕМА» under the name. */
  subtitle?: boolean
  className?: string
  subtitleClassName?: string
  /** Below 640px put DIGITAL on its own line (narrow headers). */
  stackOnMobile?: boolean
}

/** OKURMENKIDS DIGITAL — «DIGITAL» in the emerald accent. One component for every screen. */
export function BrandWordmark({ subtitle = false, className, subtitleClassName, stackOnMobile = false }: BrandWordmarkProps) {
  return (
    <span className="flex min-w-0 flex-col justify-center gap-0.5">
      <span className={cn('block truncate font-extrabold leading-none text-pd-ink', className)}>
        {BRAND.wordmark.lead} <span className={cn('text-pd-green', stackOnMobile && 'max-sm:mt-0.5 max-sm:block')}>{BRAND.wordmark.accent}</span>
      </span>
      {subtitle ? (
        <span className={cn('block font-semibold uppercase leading-[1.2] text-pd-faint [overflow-wrap:normal]', subtitleClassName)}>{BRAND.subtitle}</span>
      ) : null}
    </span>
  )
}

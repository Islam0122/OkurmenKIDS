import { useMemo } from 'react'

import { cn } from '@/utils/cn'

import { qrFor, qrSvg } from './qr'

/** An inline, scalable QR code (the SVG is built from our own matrix, no user markup). */
export function QrCode({ value, withLogo = false, logoHref = '/icons/icon-192.png', label, className }: {
  value: string
  withLogo?: boolean
  logoHref?: string
  label: string
  className?: string
}) {
  const svg = useMemo(() => qrSvg(qrFor(value, { withLogo }), { withLogo, logoHref, title: label }), [value, withLogo, logoHref, label])
  return (
    <div
      role="img"
      aria-label={label}
      className={cn('[&>svg]:block [&>svg]:h-full [&>svg]:w-full', className)}
      // eslint-disable-next-line react/no-danger -- markup generated locally from the QR matrix
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}

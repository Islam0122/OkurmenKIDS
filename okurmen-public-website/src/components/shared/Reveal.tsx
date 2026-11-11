import { motion, useReducedMotion } from 'framer-motion'
import type { ReactNode } from 'react'

/** Fade-and-rise when scrolled into view (disabled for reduced motion). */
export function Reveal({ children, delay = 0, className, as = 'div' }: { children: ReactNode; delay?: number; className?: string; as?: 'div' | 'li' | 'section' }) {
  const reduce = useReducedMotion()
  const Component = motion[as]
  if (reduce) return <Component className={className}>{children}</Component>
  return (
    <Component
      className={className}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </Component>
  )
}

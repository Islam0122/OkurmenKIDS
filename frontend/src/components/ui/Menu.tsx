import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { MoreHorizontal } from 'lucide-react'

import { cn } from '@/utils/cn'

export interface MenuItem {
  key: string
  label: string
  onClick: () => void
  icon?: ReactNode
  tone?: 'default' | 'danger'
  disabled?: boolean
}

export interface MenuProps {
  items: MenuItem[]
  align?: 'start' | 'end'
  /** Accessible label for the trigger button. */
  label?: string
}

/**
 * A small "⋯" overflow menu for secondary/destructive actions that
 * shouldn't sit as plain buttons next to the primary action row (e.g. a
 * lesson's "Отменить занятие"). Renders nothing when there are no items,
 * so callers can build `items` conditionally without an extra guard.
 */
export function Menu({ items, align = 'end', label = 'Дополнительные действия' }: MenuProps) {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isOpen) return
    function handlePointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setIsOpen(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  if (items.length === 0) return null

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label={label}
        className="flex size-9 items-center justify-center rounded-lg border border-border bg-surface text-ink-secondary hover:bg-surface-hover"
      >
        <MoreHorizontal className="size-4" aria-hidden />
      </button>

      {isOpen ? (
        <div
          role="menu"
          className={cn(
            'absolute z-20 mt-1 w-56 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg',
            align === 'end' ? 'right-0' : 'left-0',
          )}
        >
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              onClick={() => {
                setIsOpen(false)
                item.onClick()
              }}
              className={cn(
                'flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-50',
                item.tone === 'danger' ? 'text-danger' : 'text-ink',
              )}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

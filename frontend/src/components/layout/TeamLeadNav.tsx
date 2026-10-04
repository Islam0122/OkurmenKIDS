import { useEffect, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

import { cn } from '@/utils/cn'

import { activeLink, sectionOf, TEAM_LEAD_SECTIONS, TEAM_LEAD_SETTINGS } from './teamLeadNav'
import type { TeamLeadLink, TeamLeadSection } from './teamLeadNav'

const ROW = 'flex h-9 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors'
const IDLE = 'text-ink-secondary hover:bg-surface-hover hover:text-ink'
const ACTIVE = 'bg-brand-50 text-brand-700'
const ICON = 'size-[18px] shrink-0'

function NavRow({ link, active, collapsed, nested, onNavigate }: {
  link: TeamLeadLink
  active: boolean
  collapsed?: boolean
  nested?: boolean
  onNavigate?: () => void
}) {
  return (
    <Link
      to={link.to}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      title={collapsed ? link.label : undefined}
      aria-label={collapsed ? link.label : undefined}
      className={cn(ROW, active ? ACTIVE : IDLE, nested && 'h-8 pl-10 text-[13px]', collapsed && 'justify-center px-0')}
    >
      {nested ? null : <link.icon className={cn(ICON, active ? 'text-brand-600' : 'text-ink-muted')} aria-hidden />}
      {collapsed ? null : <span className="truncate">{link.label}</span>}
    </Link>
  )
}

/**
 * The Team Lead navigation: «Главная», then collapsible sections (Аналитика →
 * Группы → Тренеры → Студенты → Тесты → KPI → Отчёты), then «Настройки».
 * The section holding the current page opens by itself; others open on click.
 * `collapsed` (desktop) shows icons only — a section icon then goes to the
 * section's first page, and every icon has a tooltip with its name.
 */
export function TeamLeadNav({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const location = useLocation()
  const active = activeLink(location.pathname, location.search)
  const activeSection = sectionOf(active)
  const [open, setOpen] = useState<Set<string>>(() => new Set(activeSection ? [activeSection] : []))

  useEffect(() => {
    // Moving to a page of another section opens that section too.
    if (activeSection) setOpen((current) => (current.has(activeSection) ? current : new Set(current).add(activeSection)))
  }, [activeSection])

  const toggle = (key: string) =>
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  function renderSection(section: TeamLeadSection) {
    if (!section.children) {
      const link = { label: section.label, to: section.to as string, icon: section.icon }
      return <NavRow key={section.key} link={link} active={active === link.to} collapsed={collapsed} onNavigate={onNavigate} />
    }
    const isOpen = open.has(section.key)
    const holdsActive = activeSection === section.key
    if (collapsed) {
      const first = section.children[0]
      return (
        <Link
          key={section.key}
          to={first.to}
          onClick={onNavigate}
          title={section.label}
          aria-label={section.label}
          aria-current={holdsActive ? 'page' : undefined}
          className={cn(ROW, 'justify-center px-0', holdsActive ? ACTIVE : IDLE)}
        >
          <section.icon className={cn(ICON, holdsActive ? 'text-brand-600' : 'text-ink-muted')} aria-hidden />
        </Link>
      )
    }
    const panelId = `tl-nav-${section.key}`
    return (
      <div key={section.key}>
        <button
          type="button"
          onClick={() => toggle(section.key)}
          aria-expanded={isOpen}
          aria-controls={panelId}
          className={cn(ROW, holdsActive && !isOpen ? ACTIVE : holdsActive ? 'text-ink' : IDLE)}
        >
          <section.icon className={cn(ICON, holdsActive ? 'text-brand-600' : 'text-ink-muted')} aria-hidden />
          <span className="flex-1 truncate text-left">{section.label}</span>
          <ChevronRight className={cn('size-4 shrink-0 text-ink-muted transition-transform', isOpen && 'rotate-90')} aria-hidden />
        </button>
        {isOpen ? (
          <div id={panelId} className="mt-0.5 space-y-0.5">
            {section.children.map((child) => (
              <NavRow key={child.to} link={child} active={active === child.to} nested onNavigate={onNavigate} />
            ))}
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <nav className={cn('flex-1 space-y-0.5 overflow-y-auto py-4', collapsed ? 'px-2' : 'px-3')} aria-label="Основная навигация">
        {TEAM_LEAD_SECTIONS.map((section, index) => (
          <div key={section.key} className={index === 1 ? 'pt-2' : undefined}>{renderSection(section)}</div>
        ))}
      </nav>
      <div className={cn('space-y-0.5 border-t border-border py-3', collapsed ? 'px-2' : 'px-3')}>
        <NavRow link={TEAM_LEAD_SETTINGS} active={active === TEAM_LEAD_SETTINGS.to} collapsed={collapsed} onNavigate={onNavigate} />
      </div>
    </div>
  )
}

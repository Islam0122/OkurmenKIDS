/** Bootstrap Icons — the only icon set of the portal (no emoji). */
export function Icon({ name, className = '', label }: { name: string; className?: string; label?: string }) {
  return (
    <i
      className={`bi bi-${name} ${className}`.trim()}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? 'img' : undefined}
    />
  )
}

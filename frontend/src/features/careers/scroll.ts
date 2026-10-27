/** Прокрутка к разделу: плавная, если пользователь не просил уменьшить анимацию. */
export function scrollToSection(id: string): void {
  const el = document.getElementById(id)
  if (!el) return
  const reduce = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  el.scrollIntoView?.({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
  // Фокус — для клавиатуры и экранных дикторов, без повторной прокрутки.
  if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1')
  el.focus?.({ preventScroll: true })
}

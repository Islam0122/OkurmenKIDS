import '@testing-library/jest-dom/vitest'

// jsdom lacks these browser APIs used by framer-motion / the layout.
class IO {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return [] }
}
Object.assign(globalThis, { IntersectionObserver: IO })
window.scrollTo = () => undefined
window.matchMedia ||= ((query: string) => ({ matches: false, media: query, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false })) as typeof window.matchMedia

/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_MEDIA_URL?: string
  readonly VITE_SITE_URL?: string
  readonly VITE_USE_MOCKS?: string
  readonly VITE_CAREERS_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

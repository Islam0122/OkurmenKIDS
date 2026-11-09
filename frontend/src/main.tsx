import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from '@/App'
import { initPwa } from '@/pwa/register'

import './index.css'

const container = document.getElementById('root')
if (!container) {
  throw new Error('Root element #root was not found in index.html')
}

// Before React: the install prompt and connectivity events fire early.
initPwa()

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import 'bootstrap-icons/font/bootstrap-icons.css'
import './styles/global.css'

import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

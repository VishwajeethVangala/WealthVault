import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './styles/holdings.css'
import './styles/brokers.css'
import './styles/dashboard.css'
import './styles/signals.css'
import './styles/components.css'
import './styles/executive.css'
import './styles/account.css'
import './styles/polish.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

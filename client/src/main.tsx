import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles/tokens.css'
import './styles/dashboard.css'
import './styles/signup.css'

// The Cash dashboard is a dark-first product — pin the theme so the blueprint
// tokens resolve dark everywhere (auth, onboarding, and the app shell).
document.documentElement.setAttribute('data-theme', 'dark')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

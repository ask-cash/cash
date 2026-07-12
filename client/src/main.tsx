import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles/tokens.css'
import './styles/dashboard.css'
import './styles/signup.css'

// Cash is a light, off-white product in a monochrome palette — pin light so the
// tokens resolve the same everywhere (auth, onboarding, and the app shell),
// regardless of the OS theme.
document.documentElement.setAttribute('data-theme', 'light')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

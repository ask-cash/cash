import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/inter/wght.css'
import App from './App'
import './styles/tokens.css'
import './styles/dashboard.css'
import './styles/signup.css'

// Cash is a dark, near-black product — pin dark so the tokens resolve the same
// everywhere (auth, onboarding, and the app shell), regardless of the OS theme.
document.documentElement.setAttribute('data-theme', 'dark')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

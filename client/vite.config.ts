import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Cash dashboard client. Shares the landing site's stack (Vite + React + TS) and
// its hand-authored design system: public/styles.css is served verbatim (copied
// from landing/) so branding, gradients and typography match exactly. A dev
// proxy forwards /api to the Python gateway so the browser chat reaches Cash.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Cash dashboard client. The token and component styles are bundled by Vite;
// the dev proxy forwards /api to the Python gateway.
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

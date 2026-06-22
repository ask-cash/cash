import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// React + TypeScript landing page.
// The page's hand-authored stylesheet lives in public/styles.css (served
// verbatim, not processed by Vite's CSS pipeline) so its bespoke animations
// render exactly as designed. Fonts and logos are self-hosted in public/assets.
export default defineConfig({
  plugins: [react()],
})

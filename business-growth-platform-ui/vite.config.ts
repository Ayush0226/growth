import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {rollupOptions: {output: {manualChunks: id => /node_modules/.test(id) ? (/@supabase/.test(id) ? 'supabase' : 'vendor') : undefined}}},
})

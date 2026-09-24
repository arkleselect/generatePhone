import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
// Same-origin proxy keeps browser credentials and backend traffic on localhost.
export default defineConfig({ plugins: [vue()], server: { proxy: { '/api': 'http://127.0.0.1:8080' } } })

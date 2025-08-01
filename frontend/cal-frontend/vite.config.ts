import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // any path you call from React goes straight to FastAPI
      '/events':  'http://backend:8000',
      '/uploads': 'http://backend:8000',
    },
  },
});
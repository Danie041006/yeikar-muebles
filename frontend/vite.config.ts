import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    // PWA: service worker que precachea el shell de la app (carga al instante,
    // funciona offline para la interfaz) y cachea los catálogos estáticos con
    // NetworkFirst. El manifest se reutiliza de public/site.webmanifest.
    VitePWA({
      registerType: 'autoUpdate',
      manifest: false,
      includeAssets: ['favicon.ico', 'apple-touch-icon.png', 'Logo-yeikar.png', 'Logo-yeikar.webp'],
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,webp,svg,woff2,webmanifest}'],
        navigateFallback: '/index.html',
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        runtimeCaching: [
          {
            // Catálogos estáticos (unidades, monedas, áreas, categorías…):
            // primero red, si falla sirve la copia cacheada (útil sin internet).
            urlPattern: ({ url }) => url.pathname.startsWith('/api/v1/catalogos/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'yeikar-catalogos',
              expiration: { maxEntries: 60, maxAgeSeconds: 10 * 60 * 60 },
            },
          },
        ],
      },
    }),
  ],
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        // Code-split SOLO de librerías "hoja" (que importan react pero nada las
        // importa a ellas salvo la app): dividir react/react-dom en chunks
        // separados rompe el runtime (useState undefined). Estas tres bajan el
        // bundle principal y se cachean aparte.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('recharts') || id.includes('d3-')) return 'charts';
          if (id.includes('jspdf') || id.includes('html2canvas')) return 'pdf';
          if (id.includes('framer-motion') || id.includes('cmdk')) return 'motion';
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
    host: true,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  preview: {
    port: 4173,
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
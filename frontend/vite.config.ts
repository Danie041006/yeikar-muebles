import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // 'prompt': la versión nueva espera a que el usuario pulse "Recargar".
      // Con 'autoUpdate' el evento onNeedRefresh nunca se dispara y la app se
      // recarga sola, lo que puede perder un formulario a medio llenar.
      registerType: 'prompt',
      injectRegister: 'auto',
      // Usamos el site.webmanifest externo existente en public/; no generar otro.
      manifest: false,
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff,woff2}'],
        // El bundle principal supera los 2 MiB por defecto de Workbox.
        maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api/],
        cleanupOutdatedCaches: true,
        // Tras aceptar la actualización, el SW nuevo reclama las pestañas
        // abiertas: eso dispara el reload que aplica la versión nueva.
        clientsClaim: true,
        runtimeCaching: [
          // Dinero / fiscal / auth NUNCA se cachean: van siempre a red.
          // La función devuelve false para el resto → no intercepta → NetworkOnly
          // efectivo (el SW deja pasar a red sin cachear).
          {
            urlPattern: ({ url, request }) => {
              if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(request.method)) return true
              if (/\/api\/auth(\/|$)/.test(url.pathname)) return true
              if (
                /\/api\/v1\/(venta|pago|factura|cuenta|gasto|nomina|reporte|auditoria|users|auth|cuentas-por-pagar|cotizacion|pedido|compra|envio|cliente)(\/|$)/.test(
                  url.pathname
                )
              )
                return true
              return false
            },
            handler: 'NetworkOnly',
          },
          {
            urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts',
              expiration: {
                maxAgeSeconds: 30 * 24 * 60 * 60,
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },
          // Fotocopia con sello de hora, NO fuente de verdad: solo lectura GET del
          // taller (producto/material/produccion/inventory). La UI debe mostrar su
          // antigüedad y revalidar contra el servidor en cuanto haya red.
          {
            urlPattern: ({ url, request }) =>
              request.method === 'GET' &&
              /\/api\/v1\/(producto|material|produccion|inventory)/.test(url.pathname),
            handler: 'StaleWhileRevalidate',
            method: 'GET',
            options: {
              cacheName: 'yeikar-lectura-taller',
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 24 * 60 * 60,
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },
        ],
      },
    }),
  ],
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
  }
})

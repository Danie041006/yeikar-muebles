import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import './index.css';
import { registerSW } from 'virtual:pwa-register';

// PWA: registrar el service worker con auto-actualización — cuando hay una
// versión nueva el hook la activa (skipWaiting) y recarga la ventana, en vez
// de depender de que el usuario visite la app 2–3 veces para ver el deploy.
registerSW({ immediate: true });

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);

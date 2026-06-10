import React from 'react'
import ReactDOM from 'react-dom/client'
import './i18n'
import App from './App.jsx'
import './index.css'
import { PlatformConfigProvider } from './lib/PlatformConfigContext'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PlatformConfigProvider>
      <App />
    </PlatformConfigProvider>
  </React.StrictMode>,
)

// Offline-first is the release contract — register the service worker in every
// production build by default. Set `VITE_ENABLE_SW=false` to opt out (e.g. for
// debugging or hosts that cannot serve the worker file).
const swOptOut = import.meta.env.VITE_ENABLE_SW === 'false'
const enableServiceWorker = import.meta.env.PROD && !swOptOut

if ('serviceWorker' in navigator && enableServiceWorker) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').catch(() => {})
  })
} else if ('serviceWorker' in navigator) {
  // Clean up previously registered workers to avoid stale production caches
  // when the worker is intentionally disabled or running in dev mode.
  navigator.serviceWorker.getRegistrations().then((registrations) => {
    registrations.forEach((registration) => registration.unregister())
  })
}

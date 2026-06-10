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

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').catch(() => {})
  })
}

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import './standalone.css'

/**
 * Dev-only sign-in: `?apiKey=<your hadoku key>` once, and the dev server's proxy
 * exchanges it for the hadoku_session cookie at hadoku.me/session/create, the
 * same cookie hadoku.me itself uses. The key leaves the URL straight after.
 * Production (mounted on hadoku.me through entry.tsx) never reads this.
 */
async function devSignIn(): Promise<void> {
  if (!import.meta.env.DEV) return
  const url = new URL(window.location.href)
  const key = url.searchParams.get('apiKey')
  if (!key) return
  url.searchParams.delete('apiKey')
  window.history.replaceState(null, '', url.toString())
  const res = await fetch('/session/create', {
    method: 'POST',
    headers: { 'X-User-Key': key },
    credentials: 'include',
  })
  if (!res.ok) console.error(`[dev sign-in] /session/create answered ${res.status}`)
}

void devSignIn().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  )
})

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

const AttachmentViewer = React.lazy(() => import('./AttachmentViewer'))

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {new URLSearchParams(window.location.search).has('attachment')
      ? <React.Suspense fallback={<p role="status">Loading attachment viewer...</p>}><AttachmentViewer /></React.Suspense>
      : <App />}
  </React.StrictMode>,
)

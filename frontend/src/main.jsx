import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router'
import './index.css'
import App from './App.jsx'

// HashRouter keeps the page in the URL fragment (/#/team/12), so deep links and
// refresh work on any static host with no server-side fallback config. If you
// deploy somewhere that rewrites unknown paths to index.html, swapping this for
// BrowserRouter gives clean URLs (/team/12) -- nothing else needs to change.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </StrictMode>,
)

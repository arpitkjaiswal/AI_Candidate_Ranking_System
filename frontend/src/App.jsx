import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Jobs from './pages/Jobs'
import Rankings from './pages/Rankings'
import Candidates from './pages/Candidates'
import CandidateDetail from './pages/CandidateDetail'
import Pipeline from './pages/Pipeline'

export default function App() {
  return (
    <BrowserRouter>
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="layout">
        <Sidebar />
        <main id="main" className="main-content" tabIndex={-1}>
          <Routes>
            <Route path="/"                       element={<Dashboard />} />
            <Route path="/jobs"                   element={<Jobs />} />
            <Route path="/rankings"               element={<Rankings />} />
            <Route path="/candidates"             element={<Candidates />} />
            <Route path="/candidates/:id"         element={<CandidateDetail />} />
            <Route path="*" element={<div className="card"><h2>Page not found</h2><p>The page you requested does not exist.</p><Link to="/">Return to dashboard →</Link></div>} />
            <Route path="/pipeline"               element={<Pipeline />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

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
      <div className="layout">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/"                       element={<Dashboard />} />
            <Route path="/jobs"                   element={<Jobs />} />
            <Route path="/rankings"               element={<Rankings />} />
            <Route path="/candidates"             element={<Candidates />} />
            <Route path="/candidates/:id"         element={<CandidateDetail />} />
            <Route path="/pipeline"               element={<Pipeline />} />
            <Route path="*" element={<div className="card"><h2>Page not found</h2><p>The page you requested does not exist.</p><Link to="/">Return to dashboard</Link></div>} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

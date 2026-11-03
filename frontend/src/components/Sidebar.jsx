import { NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { checkHealth } from '../api'

const NavIcon = ({ d }) => (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
)

export default function Sidebar() {
  const [online, setOnline] = useState(null)

  useEffect(() => {
    checkHealth().then(setOnline)
    const t = setInterval(() => checkHealth().then(setOnline), 15000)
    return () => clearInterval(t)
  }, [])

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <h1>Redrob</h1>
        <span>AI Ranking Engine</span>
      </div>

      <nav className="sidebar-nav" aria-label="Main navigation">
        <span className="nav-section-label">Overview</span>
        <NavLink to="/" end className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
          <NavIcon d="M2 12V6L8 2l6 4v6l-6 4-6-4z" />
          <span>Dashboard</span>
        </NavLink>

        <span className="nav-section-label">Ranking</span>
        <NavLink to="/jobs" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
          <NavIcon d="M3 4h10M3 8h10M3 12h6" />
          <span>Jobs</span>
        </NavLink>
        <NavLink to="/rankings" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
          <NavIcon d="M1 14l4-8 4 4 3-5 3 9" />
          <span>Rankings</span>
        </NavLink>
        <NavLink to="/candidates" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
          <NavIcon d="M9 3a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM1 14s-1-6 5-6 5 6 5 6M11 7h4M13 5v4" />
          <span>Candidates</span>
        </NavLink>

        <span className="nav-section-label">System</span>
        <NavLink to="/pipeline" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
          <NavIcon d="M5 3h6l2 4-2 4H5L3 7l2-4zM8 5v4M8 11v2" />
          <span>Pipeline</span>
        </NavLink>
      </nav>

      <div className="sidebar-bottom">
        <div className="api-status">
          <span className={`status-dot ${online === null ? '' : online ? 'online' : 'offline'}`} />
          <span>API {online === null ? 'checking…' : online ? 'online' : 'offline'}</span>
        </div>
      </div>
    </aside>
  )
}

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listJobs, listPipelineRuns, listCandidates } from '../api'
import { Spinner, Badge } from '../components/UI'

function StatCard({ value, label, badge, badgeType }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {badge && <div><span className={`stat-badge ${badgeType}`}>{badge}</span></div>}
    </div>
  )
}

export default function Dashboard() {
  const [jobs, setJobs] = useState(null)
  const [runs, setRuns] = useState(null)
  const [candidateCount, setCandidateCount] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([listJobs(), listPipelineRuns(), listCandidates({ size: 1 })])
      .then(([j, r, c]) => {
        setJobs(j)
        setRuns(r)
        setCandidateCount(c.total)
      })
      .catch(e => setError(e.message))
  }, [])

  const loading = jobs === null && !error

  const doneRuns = runs?.filter(r => r.status === 'done').length ?? 0
  const runningRuns = runs?.filter(r => r.status === 'running').length ?? 0
  const lastRun = runs?.[0]
  const durations = (runs || []).filter(r => r.status === 'done' && r.started_at && r.finished_at)
    .map(r => (Date.parse(r.finished_at.replace(' ', 'T') + 'Z') - Date.parse(r.started_at.replace(' ', 'T') + 'Z')) / 1000)
    .filter(seconds => Number.isFinite(seconds) && seconds >= 0)
  const averageDuration = durations.length ? `${(durations.reduce((a, b) => a + b, 0) / durations.length).toFixed(1)}s` : '—'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div className="page-header">
        <div>
          <h2>Dashboard</h2>
          <p>Overview of your ranking engine activity</p>
        </div>
        <Link to="/pipeline" className="btn btn-primary">
          + Run Pipeline
        </Link>
      </div>

      {error && <div className="error-box">{error}</div>}

      {loading ? (
        <div className="loading-row"><Spinner /> Loading stats…</div>
      ) : (
        <>
          <div className="stat-grid">
            <StatCard
              value={candidateCount?.toLocaleString() ?? '—'}
              label="Total candidates"
              badge={candidateCount > 0 ? 'in database' : 'empty'}
              badgeType={candidateCount > 0 ? 'green' : 'amber'}
            />
            <StatCard
              value={jobs?.length ?? 0}
              label="Job postings"
              badge={`${doneRuns} ranked`}
              badgeType="blue"
            />
            <StatCard
              value={runs?.length ?? 0}
              label="Pipeline runs"
              badge={runningRuns > 0 ? `${runningRuns} running` : 'idle'}
              badgeType={runningRuns > 0 ? 'amber' : 'green'}
            />
            <StatCard
              value={averageDuration}
              label="Avg pipeline duration"
              badge="Completed runs"
              badgeType="blue"
            />
          </div>

          <div className="card">
            <div className="card-label">Recent jobs</div>
            {jobs?.length === 0 ? (
              <p style={{ color: 'var(--text3)', fontSize: 13 }}>
                No jobs yet. <Link to="/jobs">Create one →</Link>
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 4 }}>
                {jobs?.slice(0, 5).map(j => (
                  <div key={j.job_id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{j.title}</div>
                      <div style={{ fontSize: 12, color: 'var(--text3)', fontFamily: 'monospace', marginTop: 2 }}>{j.job_id}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <Badge
                        label={j.status}
                        type={j.status === 'done' ? 'green' : j.status === 'running' ? 'amber' : j.status === 'failed' ? 'red' : 'gray'}
                      />
                      <Link to={`/rankings?job=${j.job_id}`} className="btn btn-secondary btn-sm">View rankings</Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {lastRun && (
            <div className="card">
              <div className="card-label">Last pipeline run</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
                <div className="meta-row">
                  <span className="meta-key">Run ID</span>
                  <span className="td-mono">{lastRun.run_id?.slice(0, 18)}…</span>
                </div>
                <div className="meta-row">
                  <span className="meta-key">Job</span>
                  <span className="meta-val">{lastRun.job_id}</span>
                </div>
                <div className="meta-row">
                  <span className="meta-key">Status</span>
                  <Badge
                    label={lastRun.status}
                    type={lastRun.status === 'done' ? 'green' : lastRun.status === 'running' ? 'amber' : 'red'}
                  />
                </div>
                {lastRun.total_candidates && (
                  <div className="meta-row">
                    <span className="meta-key">Candidates processed</span>
                    <span className="meta-val">{lastRun.total_candidates.toLocaleString()}</span>
                  </div>
                )}
                {lastRun.started_at && (
                  <div className="meta-row">
                    <span className="meta-key">Started</span>
                    <span className="meta-val" style={{ fontSize: 12 }}>{lastRun.started_at}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

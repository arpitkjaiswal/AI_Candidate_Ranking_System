import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { listJobs, getRankings } from '../api'
import { ScoreBar, RankNum, Badge, Spinner, EmptyState } from '../components/UI'

const PAGE_SIZE = 50

export default function Rankings() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedJob = searchParams.get('job') || ''

  const [jobs, setJobs] = useState([])
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [minScore, setMinScore] = useState('')
  const [honeypots, setHoneypots] = useState(false)

  // Reset to page 1 when job/filters change
  useEffect(() => { setPage(1) }, [selectedJob, minScore, honeypots])

  useEffect(() => {
    listJobs().then(setJobs).catch(e => setError(e.message))
  }, [])

  useEffect(() => {
    if (!selectedJob) { setData(null); return }
    let active = true
    setLoading(true)
    setError(null)
    const params = { page, size: PAGE_SIZE }
    if (minScore) params.min_score = minScore
    if (honeypots) params.honeypots_only = true
    getRankings(selectedJob, params)
      .then(result => { if (active) setData(result) })
      .catch(e => { if (active) setError(e.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [selectedJob, page, minScore, honeypots]) // eslint-disable-line

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="page-header">
        <div>
          <h2>Rankings</h2>
          <p>Top candidates ranked by the ML engine composite score</p>
        </div>
      </div>

      {/* Controls */}
      <div className="filters">
        <select
          value={selectedJob}
          onChange={e => { setSearchParams({ job: e.target.value }); setPage(1) }}
          style={{ minWidth: 200 }}
        >
          <option value="">Select a job…</option>
          {jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.title} ({j.job_id})</option>)}
        </select>

        <input
          type="number"
          placeholder="Min score (0–1)"
          min={0} max={1} step={0.01}
          value={minScore}
          onChange={e => setMinScore(e.target.value)}
          style={{ width: 150 }}
        />

        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--text2)', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={honeypots}
            onChange={e => setHoneypots(e.target.checked)}
            style={{ width: 'auto', accentColor: 'var(--accent)' }}
          />
          Honeypots only
        </label>

        {selectedJob && (
          <Link to={`/pipeline?job=${selectedJob}`} className="btn btn-secondary btn-sm" style={{ marginLeft: 'auto' }}>
            Re-run pipeline
          </Link>
        )}
      </div>

      {error && <div className="error-box">{error}</div>}

      {!selectedJob ? (
        <div className="card">
          <EmptyState icon="🎯" message="Select a job above to see its ranked candidates." />
        </div>
      ) : loading ? (
        <div className="loading-row"><Spinner /> Loading rankings…</div>
      ) : data?.rankings?.length === 0 ? (
        <div className="card">
          <EmptyState icon="📭" message="No rankings found. Run the pipeline for this job first." />
        </div>
      ) : (
        <>
          {data && (
            <div style={{ fontSize: 12, color: 'var(--text3)' }}>
              Showing {data.rankings?.length} of {data.total} candidates for <strong style={{ color: 'var(--text2)' }}>{selectedJob}</strong>
            </div>
          )}

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 48 }}>Rank</th>
                  <th>Candidate</th>
                  <th>Current role</th>
                  <th style={{ width: 160 }}>Composite score</th>
                  <th style={{ width: 100 }}>Location</th>
                  <th style={{ width: 70 }}>YOE</th>
                  <th style={{ width: 70 }}>Status</th>
                  <th style={{ width: 70 }}></th>
                </tr>
              </thead>
              <tbody>
                {data?.rankings?.map(r => (
                  <tr key={r.candidate_id}>
                    <td><RankNum rank={r.rank} /></td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div className="avatar" style={{ width: 32, height: 32, fontSize: 12 }}>
                          {(r.anonymized_name || r.candidate_id).charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: 13.5 }}>{r.anonymized_name || '—'}</div>
                          <div className="td-mono" style={{ marginTop: 1 }}>{r.candidate_id}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div style={{ fontSize: 13, fontWeight: 500 }}>{r.current_title || '—'}</div>
                      <div style={{ fontSize: 11.5, color: 'var(--text3)', marginTop: 1 }}>{r.current_company || ''}</div>
                    </td>
                    <td><ScoreBar value={r.score} /></td>
                    <td style={{ fontSize: 12.5, color: 'var(--text2)' }}>{r.location || r.country || '—'}</td>
                    <td style={{ fontSize: 13, color: 'var(--text2)', fontVariantNumeric: 'tabular-nums' }}>
                      {r.years_of_experience != null ? `${r.years_of_experience}y` : '—'}
                    </td>
                    <td>
                      {r.is_honeypot
                        ? <Badge label="⚠ honeypot" type="red" />
                        : r.open_to_work
                          ? <Badge label="open" type="green" />
                          : <Badge label="passive" type="gray" />}
                    </td>
                    <td>
                      <Link to={`/candidates/${r.candidate_id}?job=${selectedJob}`} className="btn btn-secondary btn-sm">View</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>← Prev</button>
              <span className="page-info">Page {page} / {totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}


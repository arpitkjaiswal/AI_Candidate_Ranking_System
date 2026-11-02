import { useEffect, useRef, useState } from 'react'
import { listJobs, createJob } from '../api'
import { Spinner, Badge, EmptyState } from '../components/UI'
import { Link } from 'react-router-dom'

function CreateJobModal({ onClose, onCreate }) {
  const dialogRef = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    dialogRef.current?.querySelector('input')?.focus()
    return () => previous?.focus()
  }, [])

  function handleDialogKey(e) {
    if (e.key === 'Escape' && !submitting) onClose()
    if (e.key !== 'Tab') return
    const controls = [...dialogRef.current.querySelectorAll('button:not(:disabled), input, textarea')]
    const first = controls[0], last = controls[controls.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }

  const [form, setForm] = useState({ job_id: '', title: '', description: '' })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function handleSubmit(e) {
    e.preventDefault()
    if (!form.job_id || !form.title || !form.description) return
    setSubmitting(true)
    setError(null)
    try {
      const job = await createJob(form)
      onCreate(job)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="create-job-title" ref={dialogRef} onKeyDown={handleDialogKey}>
        <div className="modal-header">
          <span id="create-job-title" className="modal-title">Create job posting</span>
          <button className="modal-close" aria-label="Close dialog" onClick={onClose} disabled={submitting}>×</button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="form-group">
            <label className="form-label" htmlFor="job-id">Job ID <span style={{ color: 'var(--text3)' }}>(unique slug)</span></label>
            <input
              type="text"
              id="job-id"
              placeholder="e.g. senior-ai-eng-2024"
              value={form.job_id}
              onChange={e => set('job_id', e.target.value.toLowerCase().replace(/\s+/g, '-'))}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="job-title">Job title</label>
            <input
              type="text"
              id="job-title"
              placeholder="e.g. Senior AI Engineer"
              value={form.title}
              onChange={e => set('title', e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="job-description">Job description</label>
            <textarea id="job-description"
              placeholder="Paste the full job description here. The ML engine will use it to compute semantic similarity scores."
              value={form.description}
              onChange={e => set('description', e.target.value)}
              style={{ minHeight: 120 }}
              required
            />
          </div>

          {error && <div className="error-box">{error}</div>}

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? <><Spinner /> Creating…</> : 'Create job'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Jobs() {
  const [jobs, setJobs] = useState(null)
  const [error, setError] = useState(null)
  const [showModal, setShowModal] = useState(false)

  useEffect(() => {
    listJobs().then(setJobs).catch(e => setError(e.message))
  }, [])

  const statusColor = s => ({ done: 'green', running: 'amber', failed: 'red', pending: 'gray' }[s] || 'gray')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div className="page-header">
        <div>
          <h2>Jobs</h2>
          <p>Each job posting represents a role you're sourcing candidates for</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>+ New job</button>
      </div>

      {error && <div className="error-box">{error}</div>}

      {jobs === null && !error ? (
        <div className="loading-row"><Spinner /> Loading jobs…</div>
      ) : !jobs?.length ? (
        <div className="card">
          <EmptyState icon="📋" message="No jobs yet. Create one to get started — you'll need a job before you can run the ranking pipeline." />
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Title</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(j => (
                <tr key={j.job_id}>
                  <td><span className="td-mono">{j.job_id}</span></td>
                  <td style={{ fontWeight: 600 }}>{j.title}</td>
                  <td><Badge label={j.status} type={statusColor(j.status)} /></td>
                  <td className="td-mono">{j.created_at?.slice(0, 16) ?? '—'}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <Link to={`/rankings?job=${j.job_id}`} className="btn btn-secondary btn-sm">Rankings</Link>
                      <Link to={`/pipeline?job=${j.job_id}`} className="btn btn-secondary btn-sm">Run pipeline</Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <CreateJobModal
          onClose={() => setShowModal(false)}
          onCreate={job => setJobs(prev => [job, ...(prev || [])])}
        />
      )}
    </div>
  )
}

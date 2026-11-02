import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { listJobs, triggerPipeline, listPipelineRuns, getPipelineRun } from '../api'
import { Spinner, Badge } from '../components/UI'

function statusIcon(status) {
  const icons = { running: '⚡', done: '✓', failed: '✕', pending: '○' }
  return icons[status] || '○'
}

function statusBadgeType(s) {
  return { done: 'green', running: 'amber', failed: 'red', pending: 'gray' }[s] || 'gray'
}

export default function Pipeline() {
  const [searchParams] = useSearchParams()

  const [jobs, setJobs] = useState([])
  const [runs, setRuns] = useState([])
  const [pollingId, setPollingId] = useState(null)

  const [form, setForm] = useState({
    job_id: searchParams.get('job') || '',
    candidates_path: './candidates.jsonl',
    top_k: 100,
    embedding_mode: 'tfidf',
  })

  const [submitting, setSubmitting] = useState(false)
  const [triggerError, setTriggerError] = useState(null)
  const [triggerSuccess, setTriggerSuccess] = useState(null)


  useEffect(() => {
    listJobs().then(setJobs).catch(e => setTriggerError(e.message))
    listPipelineRuns().then(data => {
      setRuns(data)
      setPollingId(data.find(run => run.status === 'running')?.run_id || null)
    }).catch(e => setTriggerError(e.message))
  }, [])

  // Poll a running run every 3 seconds
  useEffect(() => {
    if (!pollingId) return
    const interval = setInterval(() => {
      getPipelineRun(pollingId).then(run => {
        setRuns(prev => prev.map(r => r.run_id === pollingId ? run : r))
        if (run.status !== 'running') {
          clearInterval(interval)
          setPollingId(null)
        }
      }).catch(e => setTriggerError(e.message))
    }, 3000)
    return () => clearInterval(interval)
  }, [pollingId])

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function handleRun(e) {
    e.preventDefault()
    if (!form.job_id) return
    setSubmitting(true)
    setTriggerError(null)
    setTriggerSuccess(null)
    try {
      const run = await triggerPipeline({ ...form, top_k: Number(form.top_k) })
      setRuns(prev => [run, ...prev])
      setPollingId(run.run_id)
      setTriggerSuccess(`Pipeline started! Run ID: ${run.run_id.slice(0, 18)}…`)
    } catch (err) {
      setTriggerError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const runningNow = runs.some(r => r.status === 'running')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div className="page-header">
        <div>
          <h2>Pipeline</h2>
          <p>Trigger and monitor ML ranking pipeline runs</p>
        </div>
      </div>

      <div className="pipeline-grid">
        {/* Trigger form */}
        <div className="card">
          <div className="section-title">New pipeline run</div>
          <form onSubmit={handleRun} className="pipeline-form">

            <div className="form-group">
              <label className="form-label">Job</label>
              <select value={form.job_id} onChange={e => set('job_id', e.target.value)} required>
                <option value="">Select a job…</option>
                {jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.title} ({j.job_id})</option>)}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Candidates file path <span style={{ color: 'var(--text3)' }}>(server-side)</span></label>
              <input
                type="text"
                value={form.candidates_path}
                onChange={e => set('candidates_path', e.target.value)}
                placeholder="./candidates.jsonl"
              />
              <span style={{ fontSize: 11.5, color: 'var(--text3)' }}>Relative to the project root on the server</span>
            </div>

            <div className="form-group">
              <label className="form-label">Top K candidates</label>
              <input
                type="number"
                min={1} max={1000}
                value={form.top_k}
                onChange={e => set('top_k', e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Embedding mode</label>
              <select value={form.embedding_mode} onChange={e => set('embedding_mode', e.target.value)}>
                <option value="tfidf">TF-IDF (fast, CPU, no GPU needed)</option>
                <option value="sentence_transformers">Sentence Transformers (better quality, slower)</option>
              </select>
              <span style={{ fontSize: 11.5, color: 'var(--text3)' }}>
                {form.embedding_mode === 'tfidf'
                  ? 'Good for quick testing. No torch required.'
                  : 'Requires sentence-transformers installed. Better semantic matching.'}
              </span>
            </div>

            {triggerError && <div className="error-box">{triggerError}</div>}
            {triggerSuccess && (
              <div style={{ background: 'rgba(62,207,142,.08)', border: '1px solid rgba(62,207,142,.25)', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: 'var(--green)' }}>
                {triggerSuccess}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || runningNow}
              style={{ alignSelf: 'flex-start' }}
            >
              {submitting ? <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Spinner /> Starting…</span> : runningNow ? '⚡ Pipeline running…' : '▶ Run pipeline'}
            </button>

            {runningNow && (
              <p style={{ fontSize: 12, color: 'var(--text3)' }}>
                A pipeline is already running. Wait for it to finish before starting another.
              </p>
            )}
          </form>
        </div>

        {/* Info panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <div className="section-title">What happens when you run</div>
            <ol style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingLeft: 18, marginTop: 8 }}>
              {[
                'Streams candidates from the JSONL file into the SQLite database',
                'Runs feature extraction (50+ features per candidate)',
                'Generates embeddings and computes semantic similarity',
                'Ranks all candidates using the hybrid composite scoring model',
                'Generates a 1-2 sentence reasoning for each top candidate',
                'Saves all results to the rankings table',
              ].map((step, i) => (
                <li key={i} style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6 }}>
                  {step}
                </li>
              ))}
            </ol>
          </div>

          <div className="card">
            <div className="section-title">Timing estimates</div>
            <div className="meta-list" style={{ marginTop: 8 }}>
              {[
                ['TF-IDF + 100K candidates', '~3–8 min'],
                ['Sentence Transformers (CPU)', '~15–45 min'],
                ['Sentence Transformers (GPU)', '~2–5 min'],
                ['Ranking inference only', '~2.7 sec'],
              ].map(([k, v]) => (
                <div key={k} className="meta-row">
                  <span className="meta-key" style={{ fontSize: 12.5 }}>{k}</span>
                  <span className="meta-val" style={{ fontSize: 12.5, color: 'var(--amber)' }}>{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Run history */}
      <div>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text2)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '.05em' }}>Run history</div>
        {runs.length === 0 ? (
          <div className="card">
            <p style={{ color: 'var(--text3)', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>No pipeline runs yet.</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {runs.map(r => (
              <div key={r.run_id} className="run-card">
                <div className={`run-status-icon ${r.status}`}>
                  {r.status === 'running' ? <Spinner /> : <span>{statusIcon(r.status)}</span>}
                </div>
                <div className="run-info">
                  <div className="run-label">{r.job_id}</div>
                  <div className="run-meta">
                    {r.run_id?.slice(0, 22)}… ·{' '}
                    {r.started_at?.slice(0, 16)} →{' '}
                    {r.finished_at?.slice(0, 16) || (r.status === 'running' ? 'running…' : '—')}
                    {r.total_candidates ? ` · ${r.total_candidates.toLocaleString()} candidates` : ''}
                  </div>
                  {r.error_message && (
                    <div style={{ fontSize: 12, color: 'var(--red)', marginTop: 4 }}>{r.error_message}</div>
                  )}
                </div>
                <Badge label={r.status} type={statusBadgeType(r.status)} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

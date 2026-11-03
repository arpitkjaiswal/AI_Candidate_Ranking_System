import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { listJobs, triggerPipeline, listPipelineRuns, getSystem } from '../api'
import DatasetUpload from '../components/DatasetUpload'
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
  const [startedRun, setStartedRun] = useState(null)
  const [system, setSystem] = useState(null)
  const [refreshError, setRefreshError] = useState(null)
  const [selectedDataset, setSelectedDataset] = useState(null)

  const [form, setForm] = useState({
    job_id: searchParams.get('job') || '',
    candidates_path: searchParams.get('dataset') || './candidates.jsonl',
    top_k: 100,
    embedding_mode: 'tfidf',
  })

  const [submitting, setSubmitting] = useState(false)
  const [triggerError, setTriggerError] = useState(null)
  const [triggerSuccess, setTriggerSuccess] = useState(null)


  useEffect(() => {
    const controller = new AbortController()
    let timer
    async function refresh() {
      try {
        const options = { signal: controller.signal }
        const [newJobs, newRuns, info] = await Promise.all([listJobs(options), listPipelineRuns(undefined, options), getSystem(options)])
        if (!controller.signal.aborted) {
          setJobs(newJobs); setRuns(newRuns); setSystem(info); setRefreshError(null)
        }
      } catch (error) { if (!controller.signal.aborted) setRefreshError(error.message) }
      if (!controller.signal.aborted) timer = setTimeout(refresh, 3000)
    }
    refresh()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [])

  useEffect(() => {
    const job = searchParams.get('job')
    const dataset = searchParams.get('dataset')
    if (job || dataset) setForm(previous => ({ ...previous, ...(job ? { job_id: job } : {}), ...(dataset ? { candidates_path: dataset } : {}) }))
  }, [searchParams])

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
      setStartedRun(run)
      setTriggerSuccess(`Pipeline started! Run ID: ${run.run_id.slice(0, 18)}…`)
    } catch (err) {
      setTriggerError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const runningNow = runs.some(r => r.status === 'running')
  const activeRun = runs.find(run => run.run_id === startedRun?.run_id)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div className="page-header">
        <div>
          <h2>Pipeline</h2>
          <p>Trigger and monitor ML ranking pipeline runs</p>
        </div>
      </div>

      {refreshError && <div className="error-box" role="alert">Could not refresh jobs and runs: {refreshError}</div>}
      <DatasetUpload showRunLink={false} onImported={dataset => {
        set('candidates_path', dataset.candidates_path)
        setSelectedDataset(dataset)
        setTriggerError(null)
      }} />
      <div className="pipeline-grid">
        {/* Trigger form */}
        <div className="card">
          <div className="section-title">New pipeline run</div>
          <form onSubmit={handleRun} className="pipeline-form">

            <div className="form-group">
              <label className="form-label" htmlFor="Pipeline-field-1">Job</label>
              <select id="Pipeline-field-1" value={form.job_id} onChange={e => set('job_id', e.target.value)} required>
                <option value="">Select a job…</option>
                {jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.title} ({j.job_id})</option>)}
              </select>
            </div>

            <div style={{ color: 'var(--text2)', fontSize: 13, lineHeight: 1.6 }}>
              {selectedDataset ? `Selected dataset: ${selectedDataset.filename} (${selectedDataset.total_candidates} candidates).`
                : searchParams.get('dataset') ? 'Your imported dataset is selected.'
                : 'Uses the configured candidate dataset or the profiles already in your database. Import a file above to rank a specific dataset.'}
              {!jobs.length && system && <p>No jobs yet. <Link to="/jobs">Create a job posting</Link> to get started.</p>}
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="Pipeline-field-3">Top K candidates</label>
              <input id="Pipeline-field-3"
                type="number"
                required min={1} max={1000}
                value={form.top_k}
                onChange={e => set('top_k', e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="Pipeline-field-4">Embedding mode</label>
              <select id="Pipeline-field-4" value={form.embedding_mode} onChange={e => set('embedding_mode', e.target.value)}>
                <option value="tfidf">TF-IDF (fast, CPU, no GPU needed)</option>
                {system?.embedding_modes?.includes('sentence_transformers') && <option value="sentence_transformers">Sentence Transformers</option>}
              </select>
              <span style={{ fontSize: 11.5, color: 'var(--text3)' }}>
                {form.embedding_mode === 'tfidf'
                  ? 'CPU model: fits a text vocabulary and semantic projection to the selected profiles and job description.'
                  : 'Requires sentence-transformers installed. Better semantic matching.'}
              </span>
            </div>

            {triggerError && <div className="error-box" role="alert">{triggerError}</div>}
            {triggerSuccess && (
              <div style={{ background: 'rgba(62,207,142,.08)', border: '1px solid rgba(62,207,142,.25)', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: 'var(--green)' }}>
                {triggerSuccess}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || runningNow || !form.job_id || !system}
              style={{ alignSelf: 'flex-start' }}
            >
              {submitting ? <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Spinner /> Starting…</span> : runningNow ? '⚡ Pipeline running…' : '▶ Run pipeline'}
            </button>

            {activeRun?.status === 'done' && <Link className="btn btn-secondary" to={`/rankings?job=${encodeURIComponent(activeRun.job_id)}`}>View completed rankings</Link>}
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
            <div className="section-title">Your data and model</div>
            <p style={{ color: 'var(--text2)', lineHeight: 1.7 }}>
              {system ? `${system.total_candidates.toLocaleString()} candidate profiles are available in your database. ` : 'Checking candidate availability… '}
              Ranking learns a text representation from the selected profiles and matches it to your job description.
              Results and profile evidence are saved for review. Processing time depends on the size of your dataset.
            </p>
            {system?.demo_mode && <p style={{ color: 'var(--amber)', marginTop: 10, lineHeight: 1.6 }}>
              Demo seeding is enabled. Import your own candidates above to run the model with your data.
            </p>}
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
              <div key={r.run_id} data-testid={`run-${r.run_id}`} className="run-card">
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

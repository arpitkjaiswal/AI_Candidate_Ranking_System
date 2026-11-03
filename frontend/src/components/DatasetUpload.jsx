import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { uploadDataset } from '../api'
import { Spinner } from './UI'

const MAX_BYTES = 50 * 1024 * 1024

export default function DatasetUpload({ onImported, showRunLink = true }) {
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const request = useRef(null)
  const input = useRef(null)
  useEffect(() => () => request.current?.abort(), [])

  async function handleImport(event) {
    event.preventDefault()
    if (!file) return
    setError(null)
    setResult(null)
    if (!file.name.toLowerCase().endsWith('.jsonl')) {
      setError('Choose a .jsonl file with one candidate object per line.')
      return
    }
    if (!file.size || file.size > MAX_BYTES) {
      setError('Choose a non-empty JSONL file up to 50 MiB. Larger datasets can be configured by your administrator.')
      return
    }
    const controller = new AbortController()
    request.current = controller
    setBusy(true)
    try {
      const imported = await uploadDataset(file, { signal: controller.signal })
      if (!controller.signal.aborted) {
        setResult(imported)
        setFile(null)
        if (input.current) input.current.value = ''
        onImported?.(imported)
      }
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure.message)
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return <section className="card" aria-label="Import candidates">
    <h3 className="section-title">Import your candidates</h3>
    <p style={{ color: 'var(--text2)', lineHeight: 1.6, marginBottom: 12 }}>
      Upload a JSONL file to add or update candidate profiles. Each line must contain one candidate object with
      a unique candidate_id and a profile; skills, career_history and education can be included. Maximum 50 MiB.
    </p>
    <form onSubmit={handleImport} style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
      <label className="form-label" htmlFor="candidate-dataset">Candidate JSONL file</label>
      <input ref={input} id="candidate-dataset" style={{ maxWidth: '100%', minWidth: 0 }} type="file" accept=".jsonl,application/x-ndjson" disabled={busy}
        onChange={event => { setFile(event.target.files?.[0] || null); setError(null); setResult(null) }} required />
      <button className="btn btn-primary" type="submit" disabled={busy || !file}>
        {busy ? <><Spinner /> Importing…</> : 'Import candidates'}
      </button>
    </form>
    {error && <div className="error-box" role="alert" style={{ marginTop: 12 }}>{error}</div>}
    {result && <div role="status" style={{ color: 'var(--green)', marginTop: 12 }}>
      Imported {result.total_candidates.toLocaleString()} candidates from {result.filename}.
      {showRunLink && <Link className="btn btn-secondary btn-sm" style={{ marginLeft: 12 }}
        to={`/pipeline?dataset=${encodeURIComponent(result.candidates_path)}`}>Run ranking with this dataset</Link>}
    </div>}
  </section>
}

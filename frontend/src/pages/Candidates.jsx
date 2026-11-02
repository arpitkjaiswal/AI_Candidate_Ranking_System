import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { listCandidates } from '../api'
import { Spinner, EmptyState, Badge } from '../components/UI'

const PAGE_SIZE = 50

export default function Candidates() {
  const [searchParams, setSearchParams] = useSearchParams()

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [country, setCountry] = useState(searchParams.get('country') || '')
  const [openToWork, setOpenToWork] = useState(searchParams.get('open') || '')
  const [minYoe, setMinYoe] = useState('')
  const [maxYoe, setMaxYoe] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    const params = { page, size: PAGE_SIZE }
    if (search.trim()) params.search = search.trim()
    if (country) params.country = country
    if (openToWork !== '') params.open_to_work = openToWork
    if (minYoe) params.min_yoe = minYoe
    if (maxYoe) params.max_yoe = maxYoe

    listCandidates(params)
      .then(result => { if (active) setData(result) })
      .catch(e => { if (active) setError(e.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [page, country, openToWork, minYoe, maxYoe, search])

  useEffect(() => { setPage(1) }, [country, openToWork, minYoe, maxYoe, search])

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="page-header">
        <div>
          <h2>Candidates</h2>
          <p>All candidates loaded into the system</p>
        </div>
      </div>

      <div className="filters">
        <input type="search" aria-label="Search candidates" placeholder="Search name, role or company…" value={search} onChange={e => setSearch(e.target.value)} style={{ flex: '1 1 240px' }} />
        <input
          type="text"
          placeholder="Filter by country…"
          value={country}
          onChange={e => setCountry(e.target.value)}
          style={{ width: 160 }}
        />
        <select value={openToWork} onChange={e => setOpenToWork(e.target.value)} style={{ width: 160 }}>
          <option value="">All candidates</option>
          <option value="true">Open to work</option>
          <option value="false">Not open</option>
        </select>
        <input
          type="number"
          placeholder="Min YOE"
          value={minYoe}
          onChange={e => setMinYoe(e.target.value)}
          style={{ width: 90 }}
        />
        <input
          type="number"
          placeholder="Max YOE"
          value={maxYoe}
          onChange={e => setMaxYoe(e.target.value)}
          style={{ width: 90 }}
        />
        {(search || country || openToWork || minYoe || maxYoe) && (
          <button className="btn btn-secondary btn-sm" onClick={() => {
            setSearch(''); setCountry(''); setOpenToWork(''); setMinYoe(''); setMaxYoe('')
          }}>Clear filters</button>
        )}
      </div>

      {error && <div className="error-box">{error}</div>}

      {data && (
        <div style={{ fontSize: 12, color: 'var(--text3)' }}>
          {data.total.toLocaleString()} candidate{data.total !== 1 ? 's' : ''} found
        </div>
      )}

      {loading ? (
        <div className="loading-row"><Spinner /> Loading…</div>
      ) : data?.candidates?.length === 0 ? (
        <div className="card">
          <EmptyState icon="🔍" message="No candidates match your filters. Try clearing them or run the pipeline to populate the database." />
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Current role</th>
                  <th>YOE</th>
                  <th>Location</th>
                  <th>Work mode</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data?.candidates?.map(c => (
                  <tr key={c.candidate_id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div className="avatar" style={{ width: 30, height: 30, fontSize: 11 }}>
                          {(c.anonymized_name || c.candidate_id).charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: 13.5 }}>{c.anonymized_name || '—'}</div>
                          <div className="td-mono" style={{ marginTop: 1, fontSize: 11 }}>{c.candidate_id}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div style={{ fontSize: 13, fontWeight: 500 }}>{c.current_title || '—'}</div>
                      <div style={{ fontSize: 11.5, color: 'var(--text3)' }}>{c.current_company || ''}</div>
                    </td>
                    <td style={{ fontVariantNumeric: 'tabular-nums', fontSize: 13 }}>
                      {c.years_of_experience != null ? `${c.years_of_experience}y` : '—'}
                    </td>
                    <td style={{ fontSize: 12.5, color: 'var(--text2)' }}>
                      {[c.location, c.country].filter(Boolean).join(', ') || '—'}
                    </td>
                    <td>
                      {c.preferred_work_mode
                        ? <Badge label={c.preferred_work_mode} type="blue" />
                        : <span style={{ color: 'var(--text3)', fontSize: 12 }}>—</span>}
                    </td>
                    <td>
                      {c.open_to_work
                        ? <Badge label="open" type="green" />
                        : <Badge label="passive" type="gray" />}
                    </td>
                    <td>
                      <Link to={`/candidates/${c.candidate_id}`} className="btn btn-secondary btn-sm">Profile</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button onClick={() => setPage(p => p - 1)} disabled={page === 1}>← Prev</button>
              <span className="page-info">Page {page} / {totalPages}</span>
              <button onClick={() => setPage(p => p + 1)} disabled={page === totalPages}>Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

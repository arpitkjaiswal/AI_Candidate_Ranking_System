export function ScoreBar({ value, color }) {
  const pct = Math.round(Math.max(0, Math.min(1, Number(value) || 0)) * 100)
  const clr = color || (pct >= 70 ? '#3ecf8e' : pct >= 45 ? '#5b8dee' : '#f5a623')
  return (
    <div className="score-bar-wrap">
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${pct}%`, background: clr }} />
      </div>
      <span className="score-val" style={{ color: clr }}>{pct}%</span>
    </div>
  )
}

export function RankNum({ rank }) {
  const cls = rank === 1 ? 'gold' : rank === 2 ? 'silver' : rank === 3 ? 'bronze' : ''
  return <span className={`rank-num ${cls}`}>#{rank}</span>
}

export function Badge({ label, type = 'gray' }) {
  return <span className={`badge badge-${type}`}>{label}</span>
}

export function Spinner() {
  return <span className="spinner" role="status" aria-label="Loading" />
}

export function EmptyState({ icon = '🔍', message }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <p>{message}</p>
    </div>
  )
}

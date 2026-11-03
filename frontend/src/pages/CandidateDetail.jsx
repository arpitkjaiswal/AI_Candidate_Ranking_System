import { useEffect, useState, useRef } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { getCandidate, getCandidateRanking, getCandidateFeatures } from '../api'
import { ScoreBar, Badge, Spinner } from '../components/UI'

function initials(name) {
  if (!name) return '?'
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

function formatDate(d) {
  if (!d) return '—'
  return d.slice(0, 7)
}

function featureGroup(key) {
  if (/honeypot|anomaly|stuffer/.test(key)) return 'Profile quality'
  if (/^cluster_|skill|must_have|nice_to_have|certs/.test(key)) return 'Skills'
  if (/education|degree|best_tier/.test(key)) return 'Education'
  if (/location|is_india|relocate|work_mode/.test(key)) return 'Location and work preferences'
  if (/experience|title|career|company|companies|tenure|production|consulting|current_role/.test(key)) return 'Career'
  return 'Behavioral signals'
}
function groupFeatures(features) {
  return Object.keys(features).reduce((groups, key) => {
    const group = featureGroup(key)
    ;(groups[group] ||= []).push(key)
    return groups
  }, {})
}
function featureLabel(key) {
  const text = key.replaceAll('_', ' ').replace(/\bml\b/g, 'ML').replace(/\bnlp\b/g, 'NLP').replace(/\bgithub\b/g, 'GitHub')
  return text[0].toUpperCase() + text.slice(1)
}

export default function CandidateDetail() {
  const { id } = useParams()
  const featureRequest = useRef(null)
  const [searchParams] = useSearchParams()
  const jobId = searchParams.get('job')
  const navigate = useNavigate()

  const [candidate, setCandidate] = useState(null)
  const [ranking, setRanking] = useState(null)
  const [features, setFeatures] = useState(null)
  const [featuresLoading, setFeaturesLoading] = useState(false)
  const [featureError, setFeatureError] = useState(null)
  const [activeTab, setActiveTab] = useState('profile')
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    featureRequest.current?.abort()
    // Reset all local state when navigating to a different candidate
    setCandidate(null)
    setRanking(null)
    setFeatures(null)
    setFeatureError(null)
    setFeaturesLoading(false)
    setActiveTab('profile')
    setError(null)

    getCandidate(id, { signal: controller.signal }).then(setCandidate).catch(e => { if (!controller.signal.aborted) setError(e.message) })
    if (jobId) {
      getCandidateRanking(jobId, id, { signal: controller.signal }).then(setRanking).catch(() => {})
    }
    return () => { controller.abort(); featureRequest.current?.abort() }
  }, [id, jobId])

  function loadFeatures() {
    if (features || featuresLoading) return
    setFeaturesLoading(true)
    setFeatureError(null)
    const controller = new AbortController()
    featureRequest.current = controller
    getCandidateFeatures(id, { signal: controller.signal })
      .then(d => setFeatures(d.features))
      .catch(e => { if (!controller.signal.aborted) setFeatureError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setFeaturesLoading(false) })
  }

  if (error) return <div className="error-box" style={{ margin: 20 }}>{error}</div>
  if (!candidate) return <div className="loading-row" style={{ padding: 40 }}><Spinner /> Loading candidate…</div>

  const p = candidate
  const skills = candidate.skills || []
  const career = candidate.career || []
  const education = candidate.education || []

  const componentLabels = {
    career_relevance: 'Career relevance',
    skills_match: 'Skills match',
    behavioral_signals: 'Behavioral signals',
    education_location: 'Education & location',
    semantic_similarity: 'Semantic similarity',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Back */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button className="back-btn" onClick={() => navigate(-1)}>← Back</button>
        {ranking && (
          <span style={{ fontSize: 12, color: 'var(--text3)' }}>
            Ranked <strong style={{ color: 'var(--text2)' }}>#{ranking.rank}</strong> for <span style={{ color: 'var(--accent)' }}>{jobId}</span>
          </span>
        )}
      </div>

      {/* Profile header */}
      <div className="card">
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div className="avatar" style={{ width: 56, height: 56, fontSize: 20 }}>
            {initials(p.anonymized_name)}
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{p.anonymized_name || 'Unknown'}</div>
            <div style={{ color: 'var(--text2)', marginTop: 3 }}>{p.current_title || '—'}</div>
            <div style={{ color: 'var(--text3)', fontSize: 12.5, marginTop: 2 }}>
              {p.current_company} {p.current_company_size ? `(${p.current_company_size})` : ''} · {p.current_industry || ''}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              {p.location && <Badge label={`📍 ${p.location}`} type="gray" />}
              {p.years_of_experience != null && <Badge label={`${p.years_of_experience}y exp`} type="blue" />}
              {p.open_to_work && <Badge label="Open to work" type="green" />}
              {p.willing_to_relocate && <Badge label="Can relocate" type="purple" />}
              {p.preferred_work_mode && <Badge label={p.preferred_work_mode} type="gray" />}
            </div>
          </div>

          {ranking && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 11, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Composite score</div>
              <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--accent)', lineHeight: 1.1, marginTop: 4 }}>
                {(ranking.score * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 4 }}>Rank #{ranking.rank}</div>
            </div>
          )}
        </div>
      </div>

      {/* Score breakdown */}
      {ranking && (
        <div className="card">
          <div className="section-title">Score breakdown</div>
          <div className="score-breakdown">
            {[
              ['career_relevance', ranking.career_score],
              ['skills_match', ranking.skill_score],
              ['behavioral_signals', ranking.behavioral_score],
              ['education_location', ranking.education_score],
              ['semantic_similarity', ranking.embedding_sim],
            ].map(([key, val]) => val != null ? (
              <div key={key} className="score-row">
                <span className="score-row-label">{componentLabels[key] || key}</span>
                <ScoreBar value={val} />
              </div>
            ) : null)}
          </div>
          {ranking.reasoning && (
            <div style={{ marginTop: 16 }}>
              <div className="section-title">Reasoning</div>
              <p className="reasoning-text">{ranking.reasoning}</p>
            </div>
          )}
        </div>
      )}

      {/* Tabs */}
      <div>
        <div className="tabs">
          {['profile', 'career', 'education', 'skills', 'features'].map(t => (
            <button
              key={t}
              className={`tab-btn${activeTab === t ? ' active' : ''}`}
              onClick={() => {
                setActiveTab(t)
                if (t === 'features') loadFeatures()
              }}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
              {t === 'skills' && ` (${skills.length})`}
              {t === 'career' && ` (${career.length})`}
            </button>
          ))}
        </div>

        <div className="card" style={{ borderTopLeftRadius: 0, borderTopRightRadius: 0, borderTop: 'none' }}>
          {activeTab === 'profile' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {p.headline && (
                <div>
                  <div className="section-title">Headline</div>
                  <p style={{ fontSize: 14, color: 'var(--text2)', lineHeight: 1.6 }}>{p.headline}</p>
                </div>
              )}
              {p.summary && (
                <div>
                  <div className="section-title">Summary</div>
                  <p style={{ fontSize: 13.5, color: 'var(--text2)', lineHeight: 1.7 }}>{p.summary}</p>
                </div>
              )}
              <div>
                <div className="section-title">Platform signals</div>
                <div className="meta-list">
                  {[
                    ['GitHub activity', p.github_activity_score != null ? `${p.github_activity_score}/100` : '—'],
                    ['Profile completeness', p.profile_completeness_score != null ? `${p.profile_completeness_score}%` : '—'],
                    ['Notice period', p.notice_period_days != null ? `${p.notice_period_days} days` : '—'],
                    ['Expected salary', p.expected_salary_min != null ? `₹${p.expected_salary_min}–${p.expected_salary_max} LPA` : '—'],
                    ['Verified email', p.verified_email ? '✓ Yes' : 'No'],
                    ['Verified phone', p.verified_phone ? '✓ Yes' : 'No'],
                    ['LinkedIn', p.linkedin_connected ? '✓ Connected' : 'No'],
                    ['Last active', p.last_active_date || '—'],
                  ].map(([k, v]) => (
                    <div key={k} className="meta-row">
                      <span className="meta-key">{featureLabel(k)}</span>
                      <span className="meta-val" style={{ fontSize: 13 }}>{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'career' && (
            career.length === 0
              ? <p style={{ color: 'var(--text3)', fontSize: 13 }}>No career history available.</p>
              : <div>
                {career.map((job, i) => (
                  <div key={i} className="career-item">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                      <div>
                        <div className="career-title">{job.title || '—'}</div>
                        <div className="career-company">{job.company || '—'} {job.company_size ? `· ${job.company_size}` : ''}</div>
                        <div className="career-dates">
                          {formatDate(job.start_date)} → {job.is_current ? 'Present' : formatDate(job.end_date)}
                          {job.duration_months ? ` · ${job.duration_months}mo` : ''}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                        {job.is_current && <Badge label="Current" type="green" />}
                        {job.industry && <Badge label={job.industry} type="gray" />}
                      </div>
                    </div>
                    {job.description && (
                      <p className="career-desc">{job.description.slice(0, 400)}{job.description.length > 400 ? '…' : ''}</p>
                    )}
                  </div>
                ))}
              </div>
          )}

          {activeTab === 'education' && (
            education.length === 0
              ? <p style={{ color: 'var(--text3)', fontSize: 13 }}>No education data available.</p>
              : <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                {education.map((edu, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{edu.degree || '—'} {edu.field_of_study ? `in ${edu.field_of_study}` : ''}</div>
                      <div style={{ color: 'var(--text2)', fontSize: 13, marginTop: 2 }}>{edu.institution || '—'}</div>
                      <div className="td-mono" style={{ marginTop: 3 }}>
                        {[edu.start_year, edu.end_year].filter(Boolean).join(' – ') || ''}
                        {edu.grade ? ` · Grade: ${edu.grade}` : ''}
                      </div>
                    </div>
                    {edu.tier && <Badge label={edu.tier.replace('_', ' ')} type={edu.tier === 'tier_1' ? 'amber' : edu.tier === 'tier_2' ? 'blue' : 'gray'} />}
                  </div>
                ))}
              </div>
          )}

          {activeTab === 'skills' && (
            skills.length === 0
              ? <p style={{ color: 'var(--text3)', fontSize: 13 }}>No skills data available.</p>
              : <div>
                <div className="skill-cloud">
                  {skills.map((sk, i) => (
                    <span key={i} className={`skill-tag${sk.cluster ? ' cluster' : ''}`} title={`${sk.proficiency} · ${sk.duration_months}mo · ${sk.endorsements} endorsements`}>
                      {sk.skill_name || sk.name}
                      {sk.cluster && <span style={{ fontSize: 10, opacity: .7 }}>({sk.cluster})</span>}
                    </span>
                  ))}
                </div>
              </div>
          )}

          {activeTab === 'features' && (
            featuresLoading
              ? <div className="loading-row"><Spinner /> Running feature extraction…</div>
              : !features
                ? <p style={{ color: 'var(--text3)', fontSize: 13 }}>{featureError || 'No features available for this candidate.'}</p>
                : <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  <p style={{ color: 'var(--text2)' }}>Feature values used by the ranking engine. Scores describe evidence in the profile and should be reviewed alongside the candidate’s experience.</p>
                  {Object.entries(groupFeatures(features)).map(([section, keys]) => (
                    <div key={section}>
                      <div className="section-title">{section}</div>
                      <div className="meta-list">
                        {keys.map(k => features[k] !== undefined ? (
                          <div key={k} className="meta-row">
                            <span className="meta-key" style={{ fontFamily: 'monospace', fontSize: 12 }}>{featureLabel(k)}</span>
                            <span className="meta-val" style={{ fontSize: 12.5, fontFamily: 'monospace' }}>
                              {typeof features[k] === 'object' ? JSON.stringify(features[k]).slice(0, 80) : String(features[k])}
                            </span>
                          </div>
                        ) : null)}
                      </div>
                    </div>
                  ))}
                </div>
          )}
        </div>
      </div>
    </div>
  )
}

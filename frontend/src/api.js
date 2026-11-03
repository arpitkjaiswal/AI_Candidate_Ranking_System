// frontend/src/api.js

// Backend URL
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const BASE = `${API_BASE}/api`
const HEALTH_URL = `${API_BASE}/health`

export async function req(path, options = {}) {
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...options,
      signal: options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(options.timeout ?? 30000)]) : AbortSignal.timeout(options.timeout ?? 30000),
      headers: { 'Content-Type': 'application/json', ...options.headers },
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({}))
      const detail = Array.isArray(error.detail)
        ? error.detail.map(e => `${e.loc?.slice(1).join('.') || 'Request'}: ${e.msg}`).join('; ')
        : error.detail
      throw new Error(detail || `Request failed (${res.status})`)
    }
    return await res.json()
  } catch (error) {
    if (error.name === 'TimeoutError') throw new Error('The server took too long to respond. Please try again.')
    if (error instanceof TypeError) throw new Error('Cannot reach the API. Check your connection and try again.')
    throw error
  }
}

const segment = value => encodeURIComponent(value)

// Candidates
export const listCandidates = (params = {}, options = {}) => {
  const q = new URLSearchParams(params).toString();
  return req(`/candidates${q ? `?${q}` : ""}`, options);
};

export const getCandidate = (id, options = {}) => req(`/candidates/${segment(id)}`, options);

export const getCandidateFeatures = (id, options = {}) =>
  req(`/candidates/${segment(id)}/features`, options);

// Jobs
export const listJobs = (options = {}) => req("/jobs", options);

export const getJob = (id) => req(`/jobs/${segment(id)}`);

export const createJob = (body) =>
  req("/jobs", {
    method: "POST",
    body: JSON.stringify(body),
  });

// Rankings
export const getRankings = (jobId, params = {}, options = {}) => {
  const q = new URLSearchParams(params).toString();
  return req(`/jobs/${segment(jobId)}/rankings${q ? `?${q}` : ""}`, options);
};

export const getCandidateRanking = (jobId, candidateId, options = {}) =>
  req(`/jobs/${segment(jobId)}/rankings/${segment(candidateId)}`, options);

// Pipeline
export const triggerPipeline = (body) =>
  req("/pipeline/run", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const listPipelineRuns = (jobId, options = {}) =>
  req(`/pipeline/runs${jobId ? `?job_id=${segment(jobId)}` : ""}`, options);

export const getPipelineRun = (runId) =>
  req(`/pipeline/runs/${segment(runId)}`);

// Health
export async function checkHealth() {
  try {
    const res = await fetch(HEALTH_URL, { signal: AbortSignal.timeout(5000) });
    return res.ok;
  } catch {
    return false;
  }
}

// Dataset uploads are streamed as raw JSONL, avoiding multipart or client-side parsing.
export const uploadDataset = (file, options = {}) => req(`/datasets?filename=${segment(file.name)}`, {
  ...options,
  method: 'POST',
  body: file,
  timeout: 300000,
  headers: { 'Content-Type': 'application/octet-stream' },
})
export const getSystem = (options = {}) => req('/system', options)

// frontend/src/api.js

// Backend URL
const API_BASE = (import.meta.env?.VITE_API_BASE_URL || '').replace(/\/$/, '');
const BASE = `${API_BASE}/api`;
const HEALTH_URL = `${API_BASE}/health`;

export async function req(path, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
      signal: options.signal || AbortSignal.timeout(30000),
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error(error.name === 'TimeoutError'
      ? 'The server took too long to respond. Please try again.'
      : 'Unable to reach the API. Check that the backend is running.');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    const message = Array.isArray(detail)
      ? detail.map(item => `${item.loc?.slice(1).join('.') || 'Input'}: ${item.msg}`).join('; ')
      : typeof detail === 'string' ? detail : `Request failed (${res.status})`;
    throw new Error(message);
  }
  return res.status === 204 ? null : res.json();
}

const segment = value => encodeURIComponent(value);

// Candidates
export const listCandidates = (params = {}) => {
  const q = new URLSearchParams(params).toString();
  return req(`/candidates${q ? `?${q}` : ""}`);
};

export const getCandidate = (id) => req(`/candidates/${segment(id)}`);

export const getCandidateFeatures = (id) =>
  req(`/candidates/${segment(id)}/features`);

// Jobs
export const listJobs = () => req("/jobs");

export const getJob = (id) => req(`/jobs/${segment(id)}`);

export const createJob = (body) =>
  req("/jobs", {
    method: "POST",
    body: JSON.stringify(body),
  });

// Rankings
export const getRankings = (jobId, params = {}) => {
  const q = new URLSearchParams(params).toString();
  return req(`/jobs/${segment(jobId)}/rankings${q ? `?${q}` : ""}`);
};

export const getCandidateRanking = (jobId, candidateId) =>
  req(`/jobs/${segment(jobId)}/rankings/${segment(candidateId)}`);

// Pipeline
export const triggerPipeline = (body) =>
  req("/pipeline/run", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const listPipelineRuns = (jobId) =>
  req(`/pipeline/runs${jobId ? `?job_id=${segment(jobId)}` : ""}`);

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

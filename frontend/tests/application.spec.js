import { test, expect } from '@playwright/test'

async function startAndWaitForRun(page) {
  const response = page.waitForResponse(response => response.url().endsWith('/api/pipeline/run') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '▶ Run pipeline', exact: true }).click()
  const result = await response
  expect(result.status()).toBe(202)
  const run = await result.json()
  await expect(page.getByTestId(`run-${run.run_id}`).getByText('done', { exact: true })).toBeVisible({ timeout: 30000 })
  return run
}

async function createJob(request, suffix) {
  const jobId = `browser-${suffix}-${Date.now()}`
  const response = await request.post('/api/jobs', { data: {
    job_id: jobId, title: 'Senior ML Engineer', description: 'Python ranking retrieval machine learning production systems',
  } })
  expect(response.status()).toBe(201)
  return jobId
}

test('complete recruiter journey', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByText('API online')).toBeVisible()
  await expect(page.getByText('Total candidates')).toBeVisible()
  await page.getByRole('link', { name: 'Candidates', exact: true }).click()
  await page.getByRole('link', { name: 'Profile' }).first().click()
  for (const tab of ['Career', 'Education', 'Skills']) {
    await page.getByRole('button', { name: new RegExp(`^${tab}`) }).click()
  }
  await page.getByRole('button', { name: 'Features', exact: true }).click()
  await expect(page.getByText('Estimated ML experience years', { exact: true })).toBeVisible()
  await expect(page.getByText('Honeypot score', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Jobs', exact: true }).click()
  await page.getByRole('button', { name: '+ New job' }).click()
  const job = `browser-${Date.now()}`
  await page.getByLabel('Job ID').fill(job)
  await page.getByLabel('Job title', { exact: true }).fill('Senior ML Engineer')
  await page.getByLabel('Job description', { exact: true }).fill('Python ranking retrieval machine learning production systems')
  await page.getByRole('button', { name: 'Create job', exact: true }).click()
  await expect(page.getByText(job, { exact: true })).toBeVisible()
  await page.getByRole('row').filter({ hasText: job }).getByRole('link', { name: 'Run pipeline' }).click()
  await startAndWaitForRun(page)
  await page.getByRole('link', { name: 'View completed rankings' }).click()
  await expect(page.getByRole('link', { name: 'View', exact: true }).first()).toBeVisible()
  await page.getByRole('link', { name: 'View', exact: true }).first().click()
  await expect(page.getByText('Score breakdown')).toBeVisible()
  expect(errors).toEqual([])
})

test('upload candidates and rank the imported dataset', async ({ page, request }) => {
  const job = await createJob(request, 'import')
  const suffix = Date.now()
  const candidates = [
    { candidate_id: `UPLOAD_${suffix}_1`, anonymized_name: 'Imported ML Engineer',
      profile: { headline: 'Production ML engineer', summary: 'Python machine learning ranking retrieval systems', years_of_experience: 7, country: 'India', current_title: 'ML Engineer' },
      skills: [{ name: 'Python', proficiency: 'expert', endorsements: 10, duration_months: 60 }],
      career_history: [{ company: 'Product team', title: 'ML Engineer', duration_months: 60, is_current: true, description: 'Deployed Python retrieval models in production' }], education: [], redrob_signals: {},
    },
    { candidate_id: `UPLOAD_${suffix}_2`, anonymized_name: 'Imported Sales Specialist',
      profile: { headline: 'Sales specialist', summary: 'Sales and account management for retail clients', years_of_experience: 4, country: 'India', current_title: 'Sales Specialist' },
      skills: [{ name: 'Sales', proficiency: 'advanced', endorsements: 5, duration_months: 36 }], career_history: [], education: [], redrob_signals: {},
    },
  ]
  await page.goto('/candidates')
  await page.getByLabel('Candidate JSONL file').setInputFiles({
    name: 'browser-candidates.jsonl', mimeType: 'application/x-ndjson',
    buffer: Buffer.from(candidates.map(candidate => JSON.stringify(candidate)).join('\n') + '\n'),
  })
  await page.getByRole('button', { name: 'Import candidates', exact: true }).click()
  await expect(page.getByText('Imported 2 candidates from browser-candidates.jsonl.')).toBeVisible()
  for (const candidate of candidates) {
    const profile = await request.get(`/api/candidates/${candidate.candidate_id}`)
    expect(profile.status()).toBe(200)
    expect((await profile.json()).anonymized_name).toBe(candidate.anonymized_name)
  }
  await page.getByRole('link', { name: 'Run ranking with this dataset' }).click()
  await page.getByLabel('Job', { exact: true }).selectOption(job)
  const run = await startAndWaitForRun(page)
  expect(run.job_id).toBe(job)
  await page.getByRole('link', { name: 'View completed rankings' }).click()
  await expect(page.getByRole('row').filter({ hasText: 'Imported ML Engineer' })).toBeVisible()
  const result = await (await request.get(`/api/jobs/${job}/rankings`)).json()
  expect(result.total).toBe(2)
  expect(result.rankings.map(row => row.candidate_id).sort()).toEqual(candidates.map(candidate => candidate.candidate_id).sort())
})

test('invalid upload reports the server error without changing candidate count', async ({ page, request }) => {
  const before = (await (await request.get('/api/candidates?size=1')).json()).total
  await page.goto('/candidates')
  await page.getByLabel('Candidate JSONL file').setInputFiles({ name: 'invalid.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from('not-json\n') })
  await page.getByRole('button', { name: 'Import candidates', exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  expect((await (await request.get('/api/candidates?size=1')).json()).total).toBe(before)
})

test('pipeline submission errors survive background refresh', async ({ page, request }) => {
  const job = await createJob(request, 'error')
  await page.route('**/api/pipeline/run', route => route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'Dataset is unavailable. Import a candidate file.' }) }))
  await page.goto(`/pipeline?job=${job}`)
  await page.getByRole('button', { name: '▶ Run pipeline', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Dataset is unavailable.' })).toBeVisible()
  await page.waitForResponse(response => response.url().endsWith('/api/system'))
  await expect(page.getByRole('alert').filter({ hasText: 'Dataset is unavailable.' })).toBeVisible()
})

test('rankings surfaces a failed jobs request', async ({ page }) => {
  await page.route('**/api/jobs', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Database is unavailable' }) }))
  await page.goto('/rankings')
  await expect(page.getByRole('alert')).toContainText('Could not load jobs: Database is unavailable')
})

test('mobile navigation and direct routes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  for (const route of ['/jobs', '/candidates', '/rankings', '/pipeline', '/']) {
    await page.goto(route)
    await expect(page.getByRole('heading', { level: 2 }).first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  }
  await page.goto('/nonexistent')
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
})

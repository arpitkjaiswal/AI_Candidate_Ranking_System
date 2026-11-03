import test from 'node:test';
import assert from 'node:assert/strict';
import { req, listCandidates, getCandidate, checkHealth } from '../src/api.js';

test('API requests default to the local origin and encode query parameters', async () => {
  global.fetch = async (url) => { assert.equal(url, '/api/candidates?search=Ava+Sharma'); return new Response('{"total":1}'); };
  assert.equal((await listCandidates({ search: 'Ava Sharma' })).total, 1);
});
test('candidate IDs are encoded as one path segment', async () => {
  global.fetch = async (url) => { assert.equal(url, '/api/candidates/a%2Fb'); return new Response('{}'); };
  await getCandidate('a/b');
});
test('validation errors become useful messages', async () => {
  global.fetch = async () => new Response(JSON.stringify({ detail: [{ loc: ['body', 'title'], msg: 'Required' }] }), { status: 422 });
  await assert.rejects(req('/jobs'), { message: 'title: Required' });
});
test('network and health failures are handled', async () => {
  global.fetch = async () => { throw new TypeError('Failed to fetch'); };
  await assert.rejects(req('/jobs'), /Unable to reach the API/);
  assert.equal(await checkHealth(), false);
});
test('empty successful responses are supported', async () => {
  global.fetch = async () => new Response(null, { status: 204 });
  assert.equal(await req('/jobs'), null);
});

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

beforeEach(() => vi.resetModules());
afterEach(() => vi.unstubAllEnvs());

describe('API base URL', () => {
  it.each([
    { configured: ' https://api.example.org/api/v1/// ', expected: 'https://api.example.org/api/v1' },
    { configured: ' /api/v1/// ', expected: '/api/v1' },
    { configured: '', expected: 'http://localhost:8000/api/v1' },
  ])('uses $expected for requests and exports when configured as "$configured"', async ({ configured, expected }) => {
    vi.stubEnv('VITE_API_BASE_URL', configured);
    const { api, getExportUrl } = await import('./api');
    expect(api.defaults.baseURL).toBe(expected);
    expect(getExportUrl(17, 'csv')).toBe(expected + '/analyses/17/export?format=csv');
  });

  it('keeps the local default when the variable is absent', async () => {
    vi.stubEnv('VITE_API_BASE_URL', undefined);
    const { api, getExportUrl } = await import('./api');
    expect(api.defaults.baseURL).toBe('http://localhost:8000/api/v1');
    expect(getExportUrl(17, 'json')).toBe('http://localhost:8000/api/v1/analyses/17/export?format=json');
  });
});

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AxiosError } from 'axios';
import type { InternalAxiosRequestConfig } from 'axios';
import { afterEach, describe, expect, it } from 'vitest';
import { api } from '../api';
import Standards from './Standards';

const originalAdapter = api.defaults.adapter;
afterEach(() => { cleanup(); api.defaults.adapter = originalAdapter; });

function response(config: InternalAxiosRequestConfig, data: unknown) {
  return { data, status: 200, statusText: 'OK', headers: {}, config };
}

const lifecycle = { processes: [], readiness: 'not_ready', issues: [], last_checked_at: null };
const report = {
  overall_status: 'INCOMPLETE', total_tests: 2, passed_tests: 1, failed_tests: 0,
  skipped_tests: 1, duration_seconds: 0.2,
  metrics: [{ characteristic: 'Functional suitability', criterion: 'Tests pass', method: 'pytest', status: 'not_evaluated', observed: '1/2' }],
  cases: [{ name: 'test_api', status: 'passed', message: '' }, { name: 'test_model', status: 'skipped', message: 'optional model' }],
  limitations: ['Tests do not prove ISO conformance.'],
};

describe('Standards page', () => {
  it('shows the full standard card and a real not found state', async () => {
    api.defaults.adapter = async config => response(config, config.url === '/standards/reference'
      ? [{ designation: 'ISO/IEC 25010:2023', organization: 'ISO/IEC', title: 'Product quality model',
        domain: 'Качество', purpose: 'Nine characteristics', example_use: 'Review tests',
        source_url: 'https://www.iso.org/standard/78176.html', project_evidence: ['tests/test_standards.py'] }]
      : lifecycle);
    render(<Standards />);
    expect(await screen.findByText('ISO/IEC 25010:2023')).toBeTruthy();
    expect(screen.getByText(/Nine characteristics/)).toBeTruthy();
    expect(screen.getByRole('link', { name: /Описание стандарта/ }).getAttribute('href')).toContain('iso.org');
    fireEvent.change(screen.getByPlaceholderText(/Например/), { target: { value: 'не найден' } });
    expect(screen.getByText(/Стандарты по запросу не найдены/)).toBeTruthy();
  });

  it('shows skipped tests as incomplete and clears stale results after a failed rerun', async () => {
    let runs = 0;
    api.defaults.adapter = async config => {
      if (config.url === '/standards/reference') return response(config, []);
      if (config.url === '/standards/lifecycle') return response(config, lifecycle);
      if (config.url === '/standards/quality/run') {
        runs += 1;
        if (runs === 2) throw new AxiosError('failed', AxiosError.ERR_BAD_RESPONSE, config, undefined,
          { data: { detail: 'The test runner is unavailable.' }, status: 503, statusText: 'Unavailable', headers: {}, config });
        return response(config, report);
      }
      throw new Error('Unexpected URL');
    };
    render(<Standards />);
    fireEvent.click(screen.getByRole('tab', { name: 'Качество и тесты' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Запустить тесты' }));
    expect(await screen.findByText('INCOMPLETE')).toBeTruthy();
    expect(screen.getByText('optional model')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Запустить тесты' }));
    expect(await screen.findByText('The test runner is unavailable.')).toBeTruthy();
    expect(screen.queryByText('INCOMPLETE')).toBeNull();
  });

  it('retries a failed catalog request', async () => {
    let reads = 0;
    api.defaults.adapter = async config => {
      if (config.url === '/standards/reference' && ++reads === 1) throw new Error('offline');
      return response(config, config.url === '/standards/reference' ? [] : lifecycle);
    };
    render(<Standards />);
    expect(await screen.findByRole('alert')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Повторить загрузку' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(screen.getByText(/Стандарты по запросу не найдены/)).toBeTruthy();
  });
});

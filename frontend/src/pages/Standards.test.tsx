import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AxiosError } from 'axios';
import { afterEach, describe, expect, it } from 'vitest';
import { api } from '../api';
import Standards from './Standards';

const originalAdapter = api.defaults.adapter;

afterEach(() => {
  cleanup();
  api.defaults.adapter = originalAdapter;
});

function installTransport(status: 'PASS' | 'INCOMPLETE' | 'FAIL', failSecondRun = false) {
  let runs = 0;
  api.defaults.adapter = async config => {
    if (config.method === 'get' && config.url === '/standards/reference') {
      return { data: [], status: 200, statusText: 'OK', headers: {}, config };
    }
    if (config.method === 'get' && config.url === '/standards/lifecycle') {
      return {
        data: { processes: [], readiness: 'Example', issues: [] },
        status: 200, statusText: 'OK', headers: {}, config,
      };
    }
    if (config.method === 'post' && config.url === '/standards/quality/run') {
      runs += 1;
      if (failSecondRun && runs === 2) {
        throw new AxiosError('Request failed', AxiosError.ERR_BAD_RESPONSE, config, undefined, {
          data: { detail: 'The test runner is unavailable.' },
          status: 503, statusText: 'Service Unavailable', headers: {}, config,
        });
      }
      return {
        data: {
          metrics: [{ characteristic: 'Test pass rate', score: status === 'PASS' ? 100 : 50,
            passed: status === 'PASS', details: 'passed=1, failed=0, errors=0, skipped=1, duration=0.10s' }],
          overall_status: status, total_tests: status === 'PASS' ? 1 : 2, passed_tests: 1,
        },
        status: 200, statusText: 'OK', headers: {}, config,
      };
    }
    throw new Error(`Unexpected request ${config.method} ${config.url}`);
  };
}

describe('Standards quality report', () => {
  it('clears the previous report and shows a safe API error after a failed rerun', async () => {
    installTransport('PASS', true);
    render(<Standards />);
    fireEvent.click(screen.getByRole('button', { name: 'Quality' }));
    fireEvent.click(screen.getByRole('button', { name: /Run.*Tests|Run Quality Checks/ }));
    expect(await screen.findByText(/PASS/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Run.*Tests|Run Quality Checks/ }));
    expect(await screen.findByText('The test runner is unavailable.')).toBeTruthy();
    expect(screen.queryByText(/Overall.*PASS/)).toBeNull();
    expect(screen.getByRole<HTMLButtonElement>('button', { name: /Run.*Tests|Run Quality Checks/ }).disabled).toBe(false);
  });

  it('labels skipped tests incomplete without claiming ISO certification', async () => {
    installTransport('INCOMPLETE');
    render(<Standards />);
    expect(screen.queryByText(/Verified standards/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Lifecycle' }));
    expect(await screen.findByText(/repository evidence/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Quality' }));
    fireEvent.click(screen.getByRole('button', { name: /Run.*Tests|Run Quality Checks/ }));
    await waitFor(() => expect(screen.getByText(/INCOMPLETE/)).toBeTruthy());
    expect(screen.queryByText(/certif/i)).toBeNull();
    expect(screen.getByRole('heading', { name: 'Automated Test Results' })).toBeTruthy();
  });

  it.each([
    { status: 'PASS', icon: 'Tests passed', color: 'text-green-500', score: '100.0%' },
    { status: 'INCOMPLETE', icon: 'Tests incomplete', color: 'text-amber-500', score: '50.0%' },
    { status: 'FAIL', icon: 'Tests failed', color: 'text-red-500', score: '50.0%' },
  ] as const)('shows $status metric with its own icon and percentage', async ({ status, icon, color, score }) => {
    installTransport(status);
    render(<Standards />);
    fireEvent.click(screen.getByRole('button', { name: 'Quality' }));
    fireEvent.click(screen.getByRole('button', { name: 'Run Automated Tests' }));
    expect(await screen.findByRole('img', { name: icon })).toBeTruthy();
    expect(screen.getByRole('img', { name: icon }).className).toContain(color);
    expect(screen.getByText(score)).toBeTruthy();
  });
});

describe('Standards lifecycle evidence', () => {
  it('refreshes lifecycle after a pending run and ignores an older RUNNING response', async () => {
    let releaseRun = () => {};
    let releaseOldRead = () => {};
    const runGate = new Promise<void>(resolve => { releaseRun = resolve; });
    const oldReadGate = new Promise<void>(resolve => { releaseOldRead = resolve; });
    let reads = 0;
    api.defaults.adapter = async config => {
      if (config.url === '/standards/reference') return { data: [], status: 200, statusText: 'OK', headers: {}, config };
      if (config.url === '/standards/quality/run') {
        await runGate;
        return { data: { metrics: [], overall_status: 'PASS', total_tests: 1, passed_tests: 1 }, status: 200, statusText: 'OK', headers: {}, config };
      }
      if (config.url === '/standards/lifecycle') {
        reads += 1;
        const status = reads === 1 ? 'running' : 'PASS';
        if (reads === 1) await oldReadGate;
        return { data: { processes: [{ name: 'Runtime tests', status, responsible: 'Unassigned', dependencies: [], details: status, evidence: [] }], readiness: 'Manual review required', issues: [], last_checked_at: null }, status: 200, statusText: 'OK', headers: {}, config };
      }
      throw new Error('Unexpected request');
    };
    render(<Standards />);
    fireEvent.click(screen.getByRole('button', { name: 'Quality' }));
    fireEvent.click(screen.getByRole('button', { name: 'Run Automated Tests' }));
    fireEvent.click(screen.getByRole('button', { name: 'Lifecycle' }));
    await waitFor(() => expect(reads).toBe(1));
    releaseRun();
    try {
      await waitFor(() => expect(reads).toBe(2));
      expect((await screen.findAllByText('PASS')).length).toBeGreaterThan(0);
      await act(async () => { releaseOldRead(); await oldReadGate; });
      expect(screen.queryByText('RUNNING')).toBeNull();
      expect(screen.getAllByText('PASS').length).toBeGreaterThan(0);
    } finally {
      releaseOldRead();
    }
  });

  it('offers retry after a reference catalog network error', async () => {
    let reads = 0;
    api.defaults.adapter = async config => {
      if (config.url === '/standards/reference') {
        reads += 1;
        if (reads === 1) throw new Error('network down');
        return { data: [{ designation: 'ISO/IEC 25010', organization: 'ISO/IEC', title: 'Quality model', domain: 'Quality', purpose: 'Reference', example_use: 'Review' }], status: 200, statusText: 'OK', headers: {}, config };
      }
      throw new Error('Unexpected request');
    };
    render(<Standards />);
    expect(await screen.findByRole('alert')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Retry reference' }));
    expect(await screen.findByText('ISO/IEC 25010')).toBeTruthy();
  });

  it('refreshes lifecycle after a quality run when switching tabs', async () => {
    let runs = 0;
    let reads = 0;
    api.defaults.adapter = async config => {
      if (config.url === '/standards/reference') return { data: [], status: 200, statusText: 'OK', headers: {}, config };
      if (config.url === '/standards/lifecycle') {
        reads += 1;
        return { data: { processes: [{ name: 'Runtime tests', status: runs ? 'PASS' : 'not_run', responsible: 'Unassigned', dependencies: [], evidence: [], details: runs ? 'passed=1' : 'Not run' }], readiness: 'Manual review required', issues: [], last_checked_at: runs ? '2026-10-04T00:00:00+00:00' : null }, status: 200, statusText: 'OK', headers: {}, config };
      }
      if (config.url === '/standards/quality/run') {
        runs += 1;
        return { data: { metrics: [], overall_status: 'PASS', total_tests: 1, passed_tests: 1 }, status: 200, statusText: 'OK', headers: {}, config };
      }
      throw new Error('Unexpected request');
    };
    render(<Standards />);
    fireEvent.click(screen.getByRole('button', { name: 'Lifecycle' }));
    expect(await screen.findByText('NOT RUN')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Quality' }));
    fireEvent.click(screen.getByRole('button', { name: 'Run Automated Tests' }));
    await screen.findByText(/Automated tests: PASS/);
    fireEvent.click(screen.getByRole('button', { name: 'Lifecycle' }));
    expect(await screen.findByText('passed=1')).toBeTruthy();
    await waitFor(() => expect(reads).toBe(3));
    expect(screen.getByText(/last checked/i)).toBeTruthy();
  });

  it('offers retry after a lifecycle network error', async () => {
    let reads = 0;
    api.defaults.adapter = async config => {
      if (config.url === '/standards/reference') return { data: [], status: 200, statusText: 'OK', headers: {}, config };
      if (config.url === '/standards/lifecycle') {
        reads += 1;
        if (reads === 1) throw new Error('network down');
        return { data: { processes: [], readiness: 'Manual review required', issues: [], last_checked_at: null }, status: 200, statusText: 'OK', headers: {}, config };
      }
      throw new Error('Unexpected request');
    };
    render(<Standards />);
    fireEvent.click(screen.getByRole('button', { name: 'Lifecycle' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Retry lifecycle' }));
    expect(await screen.findByText('Manual review required')).toBeTruthy();
  });
});

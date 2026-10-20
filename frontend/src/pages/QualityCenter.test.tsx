import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { InternalAxiosRequestConfig } from 'axios';
import { api } from '../api';
import QualityCenter from './QualityCenter';

const originalAdapter = api.defaults.adapter;
afterEach(() => { cleanup(); api.defaults.adapter = originalAdapter; });
const respond = (config: InternalAxiosRequestConfig, data: unknown) => ({ data, status: 200, statusText: 'OK', headers: {}, config });
const check = { id: 'backend-tests', name: 'Backend Tests', description: 'pytest', category: 'tests',
  available: true, reason: null, last_run_id: null, last_status: null, last_duration_seconds: null,
  characteristics: ['Functional suitability'], project_requirement: 'API contracts', standard_refs: ['ISO/IEC 25010:2023'] };
const run = { id: 'one', check_id: 'backend-tests', status: 'passed', created_at: '2026-10-13T12:00:00Z',
  finished_at: '2026-10-13T12:00:01Z', duration_seconds: 1, exit_code: 0,
  summary: 'Проверка завершена: passed', diagnostics: 'real output', project_version: null,
  environment: 'local', counts: { passed: 1, failed: 0, skipped: 0 },
  cases: [{ name: 'api::valid', status: 'passed', duration_seconds: 0.1, message: '' }] };

describe('Quality center', () => {
  it('shows availability and empty history without a token', async () => {
    api.defaults.adapter = async config => respond(config, config.url === '/standards/checks' ? [check] : []);
    render(<QualityCenter />);
    expect(await screen.findByRole('heading', { name: 'Backend Tests' })).toBeTruthy();
    expect(screen.getByText(/Связь с качеством: Функциональная пригодность/)).toBeTruthy();
    expect(await screen.findByText(/Сохранённых запусков пока нет/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Запустить' }).hasAttribute('disabled')).toBe(false);
  });

  it('starts a real API run and displays its cases and saved history', async () => {
    api.defaults.adapter = async config => {
      if (config.url === '/standards/checks') return respond(config, [check]);
      if (config.url === '/standards/checks/runs/history') return respond(config, [run]);
      if (config.url === '/standards/checks/backend-tests/runs') {
        expect(config.headers.get('X-Quality-Local')).toBe('1');
        return respond(config, run);
      }
      throw new Error('unexpected request');
    };
    render(<QualityCenter />);
    await screen.findByRole('heading', { name: 'Backend Tests' });
    fireEvent.click(screen.getByRole('button', { name: 'Запустить' }));
    expect(await screen.findByText('Проверка отдельного сценария проекта')).toBeTruthy();
    fireEvent.click(screen.getByText('Подробности теста'));
    expect(screen.getByText('api::valid')).toBeTruthy();
    expect(screen.getAllByText('Успешно').length).toBeGreaterThan(0);
    expect(await screen.findByText('Пройдено тестов')).toBeTruthy();
  });

  it('compares saved cases by identifier and shows incompatible checks', async () => {
    const older = { ...run, id: 'older', cases: [{ ...run.cases[0], status: 'failed' }] };
    api.defaults.adapter = async config => {
      if (config.url === '/standards/checks') return respond(config, [check]);
      if (config.url === '/standards/checks/runs/history') return respond(config, [older, run]);
      if (config.url === '/standards/checks/runs/older/compare/one') return respond(config, {
        comparable: true, first: older, second: run, reason: null, became_passed: ['api::valid'],
        became_failed: [], appeared: [], disappeared: [], duration_delta_seconds: 0,
        count_delta: { passed: 1, failed: -1, skipped: 0 },
      });
      throw new Error('unexpected request');
    };
    render(<QualityCenter />);
    await waitFor(() => expect(screen.getAllByRole('option', { name: /backend-tests/ }).length).toBe(4));
    fireEvent.change(screen.getByLabelText('Первый запуск'), { target: { value: 'older' } });
    fireEvent.change(screen.getByLabelText('Второй запуск'), { target: { value: 'one' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сравнить' }));
    expect(await screen.findByText(/Стали успешными:/)).toBeTruthy();
    expect(screen.getByText(/api::valid/)).toBeTruthy();
  });

  it('explains an unavailable tool and keeps its action disabled', async () => {
    api.defaults.adapter = async config => respond(config, [{ ...check, available: false,
      reason: 'Node.js/npm или зависимости frontend отсутствуют в этом окружении.' }]);
    render(<QualityCenter />);
    expect(await screen.findByText(/Node.js\/npm или зависимости frontend/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Запустить' }).hasAttribute('disabled')).toBe(true);
  });

  it('shows a server error from a rejected run', async () => {
    api.defaults.adapter = async config => {
      if (config.url === '/standards/checks') return respond(config, [check]);
      if (config.url === '/standards/checks/runs/history') return respond(config, []);
      if (config.url === '/standards/checks/backend-tests/runs') {
        throw { response: { data: { detail: 'Другая проверка уже выполняется' } } };
      }
      throw new Error('unexpected request');
    };
    render(<QualityCenter />);
    await screen.findByRole('heading', { name: 'Backend Tests' });
    fireEvent.click(screen.getByRole('button', { name: 'Запустить' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Другая проверка уже выполняется');
  });
});

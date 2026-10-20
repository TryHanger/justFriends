import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
const savedRun = {
  id: 'new-run', check_id: 'backend-tests', status: 'skipped', created_at: '2026-10-13T12:00:00Z',
  finished_at: '2026-10-13T12:00:02Z', duration_seconds: 2, exit_code: 0,
  summary: 'Проверка завершена', diagnostics: '', project_version: null, environment: 'local',
  counts: { passed: 1, failed: 0, skipped: 1 }, cases: [
    { name: 'test_nlp_api::test_api_persist_retrieve_and_errors', status: 'passed', duration_seconds: 0.2, message: '' },
    { name: 'test_nlp_models::test_optional_model', status: 'skipped', duration_seconds: 0, message: 'Model not installed' },
  ],
};
const measured = { standard: 'ISO/IEC 25023:2016', source_url: 'https://www.iso.org/standard/35747.html',
  measurements: [
    { id: 'backend-pass-share', title: 'Доля успешных выполненных серверных тестов', characteristic: 'Функциональная пригодность', state: 'measured', value: 100, unit: '%', numerator: 1, denominator: 1, skipped: 1, source_run_id: 'new-run', observed_at: '2026-10-13T12:00:00Z', previous_value: 75, previous_run_id: 'old-run', method: 'passed / executed × 100', limitation: 'Только сценарии pytest.' },
    { id: 'frontend-pass-share', title: 'Доля успешных выполненных тестов интерфейса', characteristic: 'Функциональная пригодность', state: 'not_measured', value: null, unit: '%', numerator: null, denominator: null, skipped: null, source_run_id: null, observed_at: null, previous_value: null, previous_run_id: null, method: 'passed / executed × 100', limitation: 'Нет запуска.' },
  ], limitations: ['Пороги не утверждены.'] };

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

  it('shows passed tests with a separate skip reason and partial ISO evidence', async () => {
    api.defaults.adapter = async config => {
      if (config.url === '/standards/reference') return response(config, []);
      if (config.url === '/standards/lifecycle') return response(config, lifecycle);
      if (config.url === '/standards/quality/measurements') return response(config, measured);
      if (config.url === '/standards/checks/runs/history') return response(config, [savedRun]);
      throw new Error('Unexpected URL');
    };
    render(<Standards />);
    fireEvent.click(screen.getByRole('tab', { name: 'Качество и тесты' }));
    expect(await screen.findByText('Тесты пройдены, 1 пропущено')).toBeTruthy();
    expect(screen.getByText('1/1')).toBeTruthy();
    expect(screen.getByText('2/9')).toBeTruthy();
    expect(screen.queryByText('INCOMPLETE')).toBeNull();
    fireEvent.click(screen.getByText('Причины пропуска: 1'));
    expect(screen.getAllByText(/Model not installed/).length).toBe(2);
    expect(screen.getByText('Сохраняет и загружает результат API; проверяет ответы при ошибках')).toBeTruthy();
    expect(screen.getByTitle('Reliability').textContent).toContain('Частично проверено');
  });

  it('shows measured values, formula and missing evidence for ISO 25023', async () => {
    api.defaults.adapter = async config => {
      if (config.url === '/standards/reference') return response(config, []);
      if (config.url === '/standards/lifecycle') return response(config, lifecycle);
      if (config.url === '/standards/checks/runs/history') return response(config, [savedRun]);
      if (config.url === '/standards/checks/runs/old-run') return response(config, { ...savedRun, id: 'old-run' });
      if (config.url === '/standards/quality/measurements') {
        expect(config.headers.get('X-Quality-Local')).toBe('1');
        return response(config, measured);
      }
      throw new Error('Unexpected URL');
    };
    render(<Standards />);
    fireEvent.click(screen.getByRole('tab', { name: 'Качество и тесты' }));
    expect(await screen.findByRole('heading', { name: /ISO\/IEC 25023:2016/ })).toBeTruthy();
    expect(await screen.findByText('100% успешно среди выполненных тестов · 1 пропущено')).toBeTruthy();
    expect(screen.getByText(/\+25 п.п. к прошлому запуску/)).toBeTruthy();
    expect(screen.getByText('Пороги не утверждены.')).toBeTruthy();
    fireEvent.click(screen.getAllByRole('button', { name: 'Предыдущий результат' })[0]);
    expect(screen.getByRole('tab', { name: 'Проверки проекта' }).getAttribute('aria-selected')).toBe('true');
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

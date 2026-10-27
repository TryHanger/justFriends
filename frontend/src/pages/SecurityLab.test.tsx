import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { api } from '../api';
import SecurityLab from './SecurityLab';

const adapter = api.defaults.adapter;
afterEach(() => { cleanup(); api.defaults.adapter = adapter; });
const result = {
  before: { findings: [{ rule: 'sql', line: 2, title: 'Динамический текст SQL-запроса', category: 'A05:2025 Injection', consequence: 'Ввод влияет на запрос', recommendation: 'Используйте параметры' }], syntax_error: null },
  after: { findings: [], syntax_error: null }, removed: 1, remaining: 0, introduced: 0,
  risk_score: 9, risk_level: 'высокий',
};

describe('Security lab', () => {
  it('submits both editable versions and clears stale evidence when input changes', async () => {
    api.defaults.adapter = async config => {
      expect(config.url).toBe('/standards/security/review');
      const body = JSON.parse(config.data);
      expect(body.before).toContain('SELECT'); expect(body.after).toContain('(name,)');
      return { config, data: result, status: 200, statusText: 'OK', headers: {} };
    };
    render(<SecurityLab />);
    expect(screen.queryByText('Предупреждения трёх правил не найдены.')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Проверить обе версии' }));
    expect(await screen.findByText('1 → 0')).toBeTruthy();
    expect(screen.getByText('Строка 2 · A05:2025 Injection')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Скачать CSV' })).toBeTruthy();
    fireEvent.change(screen.getByLabelText('После исправления'), { target: { value: 'eval(text)' } });
    expect(screen.queryByText('1 → 0')).toBeNull();
  });

  it('explains API errors and lets the user retry', async () => {
    api.defaults.adapter = async () => { throw new Error('offline'); };
    render(<SecurityLab />);
    fireEvent.click(screen.getByRole('button', { name: 'Проверить обе версии' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Проверить обе версии' }).hasAttribute('disabled')).toBe(false));
  });

  it('does not treat a syntax error as a successful fix', async () => {
    api.defaults.adapter = async config => ({ config, data: { ...result, after: { findings: [], syntax_error: 'Код не разобран.' }, removed: 0 }, status: 200, statusText: 'OK', headers: {} });
    render(<SecurityLab />);
    fireEvent.click(screen.getByRole('button', { name: 'Проверить обе версии' }));
    expect(await screen.findByText('Нет сравнения')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toBe('Код не разобран.');
    expect(screen.queryByText('Предупреждения трёх правил не найдены.')).toBeNull();
  });
});

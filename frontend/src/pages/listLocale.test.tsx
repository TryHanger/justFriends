import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AxiosError } from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import { useLanguage } from '../i18n';
import { LanguageProvider } from '../LanguageProvider';
import Dashboard from './Dashboard';
import Compare from './Compare';
import Library from './Library';

const originalAdapter = api.defaults.adapter;

function SwitchLanguage() {
  const { setLanguage } = useLanguage();
  return <button onClick={() => setLanguage('ru')}>Switch to Russian</button>;
}

function SwitchToEnglish() {
  const { setLanguage } = useLanguage();
  return <button onClick={() => setLanguage('en')}>Switch to English</button>;
}

beforeEach(() => {
  localStorage.setItem('metaphor-ui-language', 'en');
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

it('translates a failed library refresh after upload when the locale changes', async () => {
  localStorage.setItem('metaphor-ui-language', 'ru');
  let listRequests = 0;
  api.defaults.adapter = async config => {
    if (config.method === 'get' && config.url === '/library/books') {
      listRequests++;
      if (listRequests === 2) throw new AxiosError('Network Error', AxiosError.ERR_NETWORK, config);
      return { data: { items: [], total: 0 }, status: 200, statusText: 'OK', headers: {}, config };
    }
    if (config.method === 'post' && config.url === '/library/books') {
      return {
        data: { analysis_id: 1, status: 'pending', status_url: '/analyses/1' },
        status: 200, statusText: 'OK', headers: {}, config,
      };
    }
    throw new Error(`Unexpected API request: ${config.method} ${config.url}`);
  };

  const { container } = render(
    <MemoryRouter><LanguageProvider><SwitchToEnglish /><Library /></LanguageProvider></MemoryRouter>,
  );
  await waitFor(() => expect(listRequests).toBe(1));
  const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]');
  if (!fileInput) throw new Error('Book file input is missing');
  fireEvent.change(fileInput, { target: { files: [new File(['心海'], 'poem.txt', { type: 'text/plain' })] } });
  fireEvent.click(screen.getByRole('button', { name: 'Загрузить и проанализировать' }));

  expect(await screen.findByText('Не удалось загрузить библиотеку.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Switch to English' }));

  expect(await screen.findByText('Could not load the library.')).toBeTruthy();
  expect(listRequests).toBe(2);
});

afterEach(() => {
  cleanup();
  api.defaults.adapter = originalAdapter;
  localStorage.clear();
  vi.restoreAllMocks();
});

describe.each([
  { name: 'dashboard', Page: Dashboard, error: 'Не удалось загрузить историю. Проверьте доступность сервера.' },
  { name: 'comparison', Page: Compare, error: 'Не удалось загрузить историю. Проверьте доступность сервера.' },
  { name: 'library', Page: Library, error: 'Не удалось загрузить библиотеку.' },
])('$name list', ({ Page, error }) => {
  it('shows a failed request in the current locale without fetching again', async () => {
    let rejectRequest: (() => void) | undefined;
    let requests = 0;
    api.defaults.adapter = config => {
      requests++;
      return new Promise((_, reject) => {
        rejectRequest = () => reject(new AxiosError('Network Error', AxiosError.ERR_NETWORK, config));
      });
    };

    render(<MemoryRouter><LanguageProvider><SwitchLanguage /><Page /></LanguageProvider></MemoryRouter>);
    await waitFor(() => expect(requests).toBe(1));
    fireEvent.click(screen.getByRole('button', { name: 'Switch to Russian' }));
    await act(async () => { rejectRequest?.(); });

    expect(await screen.findByText(error)).toBeTruthy();
    expect(requests).toBe(1);
  });
});

import type { ComponentType } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { AxiosError } from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import { LanguageProvider } from '../LanguageProvider';
import Dashboard from './Dashboard';
import Library from './Library';
import Compare from './Compare';

const originalAdapter = api.defaults.adapter;
const validationDetails = [
  { type: 'value_error', loc: ['body', 'text'], msg: 'Text must not be whitespace only', input: '   ' },
  { type: 'literal_error', loc: ['body', 'language'], msg: 'Choose Chinese or Kazakh', input: 'xx' },
];
const validationMessage = 'Text must not be whitespace only; Choose Chinese or Kazakh';

const completedAnalyses = ['zh', 'kk'].map((language, index) => ({
  analysis_id: index + 1,
  status: 'completed',
  source_name: `${language}.txt`,
  created_at: '2026-09-28T00:00:00Z',
  result: { language, model_version: 'test', metaphors: [], needs_review: true, warnings: [] },
  error: null,
}));

type FormCase = {
  name: string;
  Page: ComponentType;
  buttonName: string;
  fallback: string;
  prepare: (container: HTMLElement) => void | Promise<void>;
};

const forms: FormCase[] = [
  {
    name: 'analysis', Page: Dashboard, buttonName: 'Analyze', fallback: 'Failed to submit analysis.',
    prepare: () => { fireEvent.change(screen.getByRole('textbox'), { target: { value: '   ' } }); },
  },
  {
    name: 'library', Page: Library, buttonName: 'Upload and analyze', fallback: 'Could not upload the book.',
    prepare: (container) => {
      const input = container.querySelector<HTMLInputElement>('input[type="file"]');
      if (!input) throw new Error('Book upload input is missing');
      fireEvent.change(input, { target: { files: [new File(['心海'], 'poem.txt', { type: 'text/plain' })] } });
    },
  },
  {
    name: 'comparison', Page: Compare, buttonName: 'Compare Selected', fallback: 'Failed to compare.',
    prepare: async () => {
      const checkboxes = await screen.findAllByRole('checkbox');
      checkboxes.forEach(checkbox => fireEvent.click(checkbox));
    },
  },
];

beforeEach(() => {
  localStorage.setItem('metaphor-ui-language', 'en');
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  api.defaults.adapter = originalAdapter;
  localStorage.clear();
  vi.restoreAllMocks();
});

function rejectSubmissions(detail: unknown, networkError = false) {
  // Keep the real API functions and Axios client; replace only the HTTP transport.
  api.defaults.adapter = async (config) => {
    if (config.method === 'get') {
      const data = config.url === '/library/books'
        ? { items: [], total: 0 }
        : { items: completedAnalyses, limit: 20, offset: 0 };
      return { data, status: 200, statusText: 'OK', headers: {}, config };
    }
    if (networkError) throw new AxiosError('Network Error', AxiosError.ERR_NETWORK, config);
    throw new AxiosError('Request failed', AxiosError.ERR_BAD_REQUEST, config, undefined, {
      data: { detail }, status: 422, statusText: 'Unprocessable Entity', headers: {}, config,
    });
  };
}

describe.each(forms)('$name form', ({ Page, buttonName, fallback, prepare }) => {
  it.each([
    { scenario: 'validation details', detail: validationDetails, message: validationMessage },
    { scenario: 'plain error text', detail: 'File exceeds 20 MB', message: 'File exceeds 20 MB' },
    { scenario: 'unrecognized details', detail: { internal: 'private diagnostic' }, message: null },
    { scenario: 'a network failure', detail: undefined, message: null, networkError: true },
  ])('shows $scenario and keeps the form usable', async ({ detail, message, networkError }) => {
    rejectSubmissions(detail, networkError);
    const { container } = render(
      <MemoryRouter><LanguageProvider><Page /></LanguageProvider></MemoryRouter>,
    );
    await prepare(container);
    fireEvent.click(screen.getByRole('button', { name: buttonName }));

    expect(await screen.findByText(message ?? fallback)).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>('button', { name: buttonName }).disabled).toBe(false);
    expect(screen.queryByText(/private diagnostic/)).toBeNull();
  });
});

describe.each([
  { page: 'dashboard', Page: Dashboard },
  { page: 'comparison', Page: Compare },
])('$page history loading', ({ Page }) => {
  it.each([
    { language: 'en', expected: 'Could not load analysis history. Check that the backend is available.' },
    { language: 'ru', expected: 'Не удалось загрузить историю. Проверьте доступность сервера.' },
  ])('uses a backend-neutral $language error when history cannot be loaded', async ({ language, expected }) => {
    localStorage.setItem('metaphor-ui-language', language);
    api.defaults.adapter = async config => {
      throw new AxiosError('Network Error', AxiosError.ERR_NETWORK, config);
    };
    render(<MemoryRouter><LanguageProvider><Page /></LanguageProvider></MemoryRouter>);

    expect(await screen.findByText(expected)).toBeTruthy();
    expect(screen.queryByText(/localhost:8000/)).toBeNull();
  });
});

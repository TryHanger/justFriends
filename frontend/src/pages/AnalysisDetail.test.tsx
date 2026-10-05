import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { api } from '../api';
import type { AnalysisResponse, AnalysisResult } from '../api';
import { LanguageProvider } from '../LanguageProvider';
import AnalysisDetail from './AnalysisDetail';

const originalAdapter = api.defaults.adapter;
const metaphor = {
  text: 'The moon is a boat', start: 0, end: 18, label: 'metaphor',
  source_domain: 'journey', target_domain: 'nature', confidence: 0.8,
  rationale: 'Boat imagery describes the moon.',
};

function showResult(result: AnalysisResult, language: 'en' | 'ru' = 'en') {
  localStorage.setItem('metaphor-ui-language', language);
  const response: AnalysisResponse = {
    analysis_id: 17, status: 'completed', source_name: 'poem.txt',
    created_at: '2026-09-28T00:00:00Z', result, error: null,
  };
  api.defaults.adapter = async config => ({
    data: response, status: 200, statusText: 'OK', headers: {}, config,
  });
  return render(
    <MemoryRouter initialEntries={['/analyses/17']}>
      <LanguageProvider>
        <Routes><Route path="/analyses/:id" element={<AnalysisDetail />} /></Routes>
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  api.defaults.adapter = originalAdapter;
  localStorage.clear();
});

describe('completed analysis warnings', () => {
  it('shows the review notice and every model warning as plain text', async () => {
    showResult({
      language: 'zh', model_version: 'test', metaphors: [metaphor], needs_review: true,
      warnings: ['Check segment boundaries', '<script>alert("x")</script>'],
    });
    expect(await screen.findByText('This analysis needs manual review.')).toBeTruthy();
    expect(screen.getByText('Check segment boundaries')).toBeTruthy();
    expect(screen.getByText('<script>alert("x")</script>')).toBeTruthy();
    expect(document.querySelector('script')).toBeNull();
    expect(screen.getByText('Found Metaphors (1)')).toBeTruthy();
  });

  it('keeps warnings visible with zero metaphors and translates the notice', async () => {
    showResult({
      language: 'kk', model_version: 'test', metaphors: [], needs_review: true,
      warnings: ['Проверьте транслитерацию'],
    }, 'ru');
    expect(await screen.findByText('Требуется ручная проверка анализа.')).toBeTruthy();
    expect(screen.getByText('Проверьте транслитерацию')).toBeTruthy();
    expect(screen.getByText('В документе метафоры не обнаружены.')).toBeTruthy();
  });

  it('shows returned warnings even when review is not requested', async () => {
    showResult({
      language: 'zh', model_version: 'test', metaphors: [], warnings: ['Low confidence'],
    });
    expect(await screen.findByText('Low confidence')).toBeTruthy();
    expect(screen.queryByText('This analysis needs manual review.')).toBeNull();
  });

  it('renders a legacy result without a warning banner', async () => {
    showResult({ language: 'zh', model_version: 'test', metaphors: [] });
    expect(await screen.findByText('Found Metaphors (0)')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders false and empty warnings without a warning banner', async () => {
    showResult({
      language: 'zh', model_version: 'test', metaphors: [], needs_review: false, warnings: [],
    });
    expect(await screen.findByText('Found Metaphors (0)')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

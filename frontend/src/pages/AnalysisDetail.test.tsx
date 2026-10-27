import { cleanup, render, screen, within } from '@testing-library/react';
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

  it('shows the calibration statement as a note, not as a warning', async () => {
    showResult({
      language: 'zh', model_version: 'test', metaphors: [metaphor], needs_review: false,
      warnings: ['Confidence calibrated on CMDAG (1292 figures): the probability that a figure is correct.'],
    }, 'ru');
    expect(await screen.findByText(/Уверенность откалибрована на экспертных данных \(эталон CMDAG, 1292 фигур\)/)).toBeTruthy();
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

describe('stanza types', () => {
  const stanzas = [
    { text: '关关雎鸠，\n在河之洲。', start: 0, end: 11, label: '興' as const, probabilities: { '賦': 0.1, '比': 0.2, '興': 0.7 } },
    { text: '参差荇菜，左右流之。', start: 13, end: 23, label: '賦' as const, probabilities: { '賦': 0.55, '比': 0.3, '興': 0.15 } },
  ];

  it('shows each stanza label in Russian with its probability as a model suggestion', async () => {
    showResult({ language: 'zh', model_version: 'test', metaphors: [], stanzas }, 'ru');
    expect(await screen.findByText('Строфы (2)')).toBeTruthy();
    expect(screen.getByText(/подсказки модели, а не экспертная разметка/)).toBeTruthy();
    expect(screen.getByText('興 — «образ-зачин»')).toBeTruthy();
    expect(screen.getByText('вероятность 70%')).toBeTruthy();
    expect(screen.getByText('賦 — «описание»')).toBeTruthy();
    expect(screen.getByText('вероятность 55%')).toBeTruthy();
    expect(screen.getByText('关关雎鸠，').getAttribute('title')).toBe('关关雎鸠，\n在河之洲。');
  });

  it('hides the block for Kazakh and for results without stanzas', async () => {
    showResult({ language: 'kk', model_version: 'test', metaphors: [], stanzas }, 'ru');
    expect(await screen.findByText('Найденные метафоры (0)')).toBeTruthy();
    expect(screen.queryByText(/Строфы/)).toBeNull();
    cleanup();
    showResult({ language: 'zh', model_version: 'test', metaphors: [] }, 'ru');
    expect(await screen.findByText('Найденные метафоры (0)')).toBeTruthy();
    expect(screen.queryByText(/Строфы/)).toBeNull();
  });
});

describe('detector badges', () => {
  const figure = (text: string, start: number, end: number) => ({ ...metaphor, text, start, end });
  const metaphors = [figure('春风又绿', 0, 4), figure('明月', 8, 10), figure('照我', 12, 14)];
  const sources = { '0-4': ['llm', 'xlmr'], '8-10': ['llm'], '12-14': ['xlmr'] };

  it('shows which detector found each figure of a unified result', async () => {
    showResult({
      language: 'zh', model_version: 'unified(openai:gpt-4o-mini,xlmr-zh-gold-v2)', metaphors,
      method: { unified: { xlmr_model: 'xlmr-zh-gold-v2', sources, both: 1, llm_only: 1, xlmr_only: 1 } },
    }, 'ru');
    expect(await screen.findByText('GPT и XLM-R')).toBeTruthy();
    expect(screen.getByText('только GPT')).toBeTruthy();
    expect(screen.getByText('только XLM-R')).toBeTruthy();
    const card = screen.getByText('"照我"').parentElement as HTMLElement;
    expect(within(card).getByText('только XLM-R')).toBeTruthy();
  });

  it('hides source badges when XLM-R did not run and translates the warning', async () => {
    showResult({
      language: 'kk', model_version: 'unified(openai:gpt-4o-mini)', metaphors: [metaphor],
      warnings: ['Unified model: XLM-R for kk is not installed (weights or PyTorch missing); only LLM figures are shown.'],
      method: { unified: { xlmr_model: null, sources: { '0-18': ['llm'] }, both: 0, llm_only: 1, xlmr_only: 0 } },
    }, 'ru');
    expect(await screen.findByText('Единая модель: XLM-R для казахского не установлена (нет весов или PyTorch); показаны только фигуры GPT.')).toBeTruthy();
    expect(screen.queryByText('только GPT')).toBeNull();
  });

  it('marks figures added by the classical mode or the direct usage question', async () => {
    showResult({
      language: 'zh', model_version: 'openai:gpt-4o-mini', metaphors,
      method: { classical: { added: [[8, 10]] }, two_stage: { added: [[12, 14]], disputed: [[0, 4]] } },
    }, 'ru');
    expect(await screen.findByText('классический режим')).toBeTruthy();
    expect(screen.getByText('добавлено прямым вопросом')).toBeTruthy();
    expect(screen.getByText('второй этап: прямое значение')).toBeTruthy();
    expect(screen.queryByText(/только/)).toBeNull();
  });
});

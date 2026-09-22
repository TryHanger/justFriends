import axios from 'axios';

const API_BASE = 'http://localhost:8000/api/v1';

export const api = axios.create({
  baseURL: API_BASE,
});

export interface Metaphor {
  text: string;
  start: number;
  end: number;
  label: string;
  source_domain: string;
  target_domain: string;
  confidence: number;
  rationale: string;
}

export interface AnalysisResult {
  language: string;
  model_version: string;
  metaphors: Metaphor[];
}

export interface AnalysisResponse {
  analysis_id: number;
  status: string;
  source_name: string | null;
  created_at: string;
  result: AnalysisResult | null;
  error: string | null;
}

export interface AnalysisListResponse {
  items: AnalysisResponse[];
  limit: number;
  offset: number;
}

export interface ComparisonGroup {
  analysis_count: number;
  metaphor_count: number;
  by_label: Record<string, number>;
  by_source_domain: Record<string, number>;
  by_target_domain: Record<string, number>;
}

export interface AggregateCompareResponse {
  languages: Record<string, ComparisonGroup>;
  analysis_ids: number[];
  note: string;
}

export interface SemanticMatch {
  query_id: string;
  candidate_id: string;
  similarity: number;
  rank: number;
}

export interface SemanticCompareResponse {
  model_version: string;
  matches: SemanticMatch[];
  warnings: string[];
}

export interface LibraryBook {
  id: number;
  title: string;
  author: string | null;
  language: string;
  source_name: string;
  source_url: string | null;
  analysis_id: number;
  status: string;
  created_at: string;
  result: AnalysisResult | null;
}

export interface SubmitResponse {
  analysis_id: number;
  status: string;
  status_url: string;
}

export const submitText = async (text: string, language: string = 'auto') => {
  const res = await api.post<SubmitResponse>('/analyze', { text, language });
  return res.data;
};

export const submitFile = async (file: File, language: string = 'auto') => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('language', language);
  const res = await api.post<SubmitResponse>('/analyze/file', formData);
  return res.data;
};

export const getAnalysis = async (id: number) => {
  const res = await api.get<AnalysisResponse>(`/analyses/${id}`);
  return res.data;
};

export const listAnalyses = async (limit = 20, offset = 0) => {
  const res = await api.get<AnalysisListResponse>(`/analyses`, { params: { limit, offset } });
  return res.data;
};

export const compareAnalyses = async (analysisIds: number[]) => {
  const res = await api.post<AggregateCompareResponse>('/compare', { analysis_ids: analysisIds });
  return res.data;
};

export const compareSemanticAnalyses = async (analysisIds: number[], k = 5) => {
  const res = await api.post<SemanticCompareResponse>(`/compare/semantic?k=${k}`, {
    analysis_ids: analysisIds,
  });
  return res.data;
};

export const listLibraryBooks = async () => {
  const res = await api.get<{ items: LibraryBook[]; total: number }>('/library/books');
  return res.data;
};

export const uploadLibraryBook = async (file: File, language = 'auto', title = '', author = '', sourceUrl = '') => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('language', language);
  if (title) formData.append('title', title);
  if (author) formData.append('author', author);
  if (sourceUrl) formData.append('source_url', sourceUrl);
  const res = await api.post<SubmitResponse>('/library/books', formData);
  return res.data;
};

export const getExportUrl = (id: number, format: 'json' | 'csv') => {
  return `${API_BASE}/analyses/${id}/export?format=${format}`;
};

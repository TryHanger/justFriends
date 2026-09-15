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
  const res = await api.get<AnalysisResponse[]>(`/analyses`, { params: { limit, offset } });
  return res.data;
};

export const compareAnalyses = async (analysisIds: number[]) => {
  const res = await api.post('/compare', { analysis_ids: analysisIds });
  return res.data;
};

export const getExportUrl = (id: number, format: 'json' | 'csv') => {
  return `${API_BASE}/analyses/${id}/export?format=${format}`;
};

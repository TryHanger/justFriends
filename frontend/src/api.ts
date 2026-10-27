import axios from 'axios';

const API_BASE = ((import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_BASE ?? '').trim() || '/api/v1').replace(/\/+$/, '');

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
  // ТЗ п. 4.1 fields; absent in results of older analyses and non-LLM detectors.
  entity?: string | null;
  entity_type?: string | null;
  usage_type?: 'metaphorical' | 'literal';
  context_sentence?: string | null;
  semantic_label?: string | null;
  sentiment?: 'positive' | 'neutral' | 'negative' | null;
  tenor?: string | null;
  tenor_start?: number | null;
  tenor_end?: number | null;
  ground?: string | null;
}

export interface EntityCandidate {
  text: string;
  start: number;
  end: number;
  entity_type: string;
  usage_type: 'metaphorical' | 'literal' | null;
  origin: string;
  lexicon_meaning?: string | null;
  reasoning?: string | null;
}

export type StanzaType = '賦' | '比' | '興';

export interface StanzaLabel {
  text: string;
  start: number;
  end: number;
  label: StanzaType;
  probabilities: Partial<Record<StanzaType, number>>;
}

export interface AnalysisResult {
  language: string;
  model_version: string;
  metaphors: Metaphor[];
  needs_review?: boolean;
  warnings?: string[];
  candidates?: EntityCandidate[];
  method?: Record<string, unknown>;
  stanzas?: StanzaLabel[];
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

export type ModelProfile = 'default' | 'experimental_kk' | 'xlmr_zh_gold_v2' | 'unified' | 'baseline';

export interface ModelInfo {
  id: ModelProfile;
  name: string;
  description: string;
  languages: Array<'auto' | 'zh' | 'kk'>;
  supervision: string;
  training_records?: number | null;
  metric_label?: string | null;
  metric_value?: number | null;
  available: boolean;
}

export const submitText = async (text: string, language: string = 'auto', modelProfile: ModelProfile = 'default') => {
  const res = await api.post<SubmitResponse>('/analyze', { text, language, model_profile: modelProfile });
  return res.data;
};

export const submitFile = async (file: File, language: string = 'auto', modelProfile: ModelProfile = 'default') => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('language', language);
  formData.append('model_profile', modelProfile);
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

export const listModels = async () => {
  const res = await api.get<ModelInfo[]>('/models');
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

export const getExportUrl = (id: number, format: 'json' | 'csv' | 'tz') => {
  return `${API_BASE}/analyses/${id}/export?format=${format}`;
};

export interface StandardInfo {
  designation: string;
  organization: string;
  title: string;
  domain: string;
  purpose: string;
  example_use: string;
  source_url: string;
  project_evidence: string[];
}

export interface SecurityFinding {
  rule: string; line: number; title: string; category: string;
  consequence: string; recommendation: string;
}
export interface SecurityReview {
  before: { findings: SecurityFinding[]; syntax_error: string | null };
  after: { findings: SecurityFinding[]; syntax_error: string | null };
  removed: number; remaining: number; introduced: number;
  risk_score: number; risk_level: string;
}
export const reviewSecurity = async (before: string, after: string, likelihood: number, impact: number) =>
  (await api.post<SecurityReview>('/standards/security/review', { before, after, likelihood, impact })).data;

export interface LifecycleProcess {
  id: string;
  name: string;
  status: 'evidenced' | 'partial' | 'missing';
  responsible: string;
  inputs: string[];
  outputs: string[];
  dependencies: string[];
  evidence: string[];
  gaps: string[];
  details?: string;
}

export interface LifecycleState {
  processes: LifecycleProcess[];
  readiness: 'not_ready' | 'conditional' | 'ready';
  issues: string[];
  last_checked_at?: string | null;
}

export interface QualityMetric {
  characteristic: string;
  criterion: string;
  method: string;
  status: 'passed' | 'failed' | 'not_evaluated';
  observed: string;
}

export interface QualityCase {
  name: string;
  status: 'passed' | 'failed' | 'error' | 'skipped';
  message: string;
}

export interface QualityReport {
  metrics: QualityMetric[];
  overall_status: 'PASS' | 'FAIL' | 'INCOMPLETE';
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  skipped_tests: number;
  duration_seconds: number;
  cases: QualityCase[];
  limitations: string[];
}

export interface ProductMeasurement {
  id: string; title: string; characteristic: string;
  state: 'measured' | 'not_measured'; value: number | null; unit: string;
  numerator: number | null; denominator: number | null; skipped: number | null;
  source_run_id: string | null; observed_at: string | null;
  previous_value?: number | null; previous_run_id?: string | null; previous_observed_at?: string | null;
  method: string; limitation: string;
}
export interface ProductMeasurementsReport {
  standard: string; source_url: string;
  measurements: ProductMeasurement[]; limitations: string[];
}

export const getStandardsReference = async () => {
  const res = await api.get<StandardInfo[]>('/standards/reference');
  return res.data;
};

export const getLifecycleState = async () => {
  const res = await api.get<LifecycleState>('/standards/lifecycle');
  return res.data;
};

const localCheckHeaders = { 'X-Quality-Local': '1' };
export const runQualityChecks = async () => {
  const res = await api.post<QualityReport>('/standards/quality/run', null, { headers: localCheckHeaders });
  return res.data;
};

export const getProductMeasurements = async () =>
  (await api.get<ProductMeasurementsReport>('/standards/quality/measurements', {
    headers: localCheckHeaders,
  })).data;

export type CheckStatus = 'queued' | 'running' | 'passed' | 'failed' | 'skipped' | 'unavailable' | 'timeout' | 'error' | 'interrupted';
export interface ProjectCheck {
  id: string; name: string; description: string; category: string;
  available: boolean; reason: string | null; last_run_id: string | null;
  last_status: CheckStatus | null; last_duration_seconds: number | null;
  characteristics: string[];
  project_requirement: string; standard_refs: string[];
}
export interface CheckCase { name: string; status: string; duration_seconds: number; message: string }
export interface CheckRun {
  id: string; check_id: string; status: CheckStatus; created_at: string;
  finished_at: string | null; duration_seconds: number | null; exit_code: number | null;
  summary: string; diagnostics: string; cases: CheckCase[];
  counts: Record<string, number>; project_version: string | null; environment: string;
}
export interface CheckComparison {
  comparable: boolean; reason: string | null; first: CheckRun; second: CheckRun;
  became_passed?: string[]; became_failed?: string[]; appeared?: string[]; disappeared?: string[];
  duration_delta_seconds?: number; count_delta?: Record<string, number>;
}
export const listProjectChecks = async () => (await api.get<ProjectCheck[]>('/standards/checks')).data;
export const listCheckRuns = async (check_id?: string, status?: string) =>
  (await api.get<CheckRun[]>('/standards/checks/runs/history', {
    headers: localCheckHeaders, params: { check_id: check_id || undefined, status: status || undefined },
  })).data;
export const startCheckRun = async (checkId: string) =>
  (await api.post<CheckRun>(`/standards/checks/${checkId}/runs`, null, { headers: localCheckHeaders })).data;
export const getCheckRun = async (id: string) =>
  (await api.get<CheckRun>(`/standards/checks/runs/${id}`, { headers: localCheckHeaders })).data;
export const compareCheckRuns = async (first: string, second: string) =>
  (await api.get<CheckComparison>(`/standards/checks/runs/${first}/compare/${second}`, { headers: localCheckHeaders })).data;


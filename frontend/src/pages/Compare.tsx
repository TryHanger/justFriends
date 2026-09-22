import { useState, useEffect, useMemo } from 'react';
import { listAnalyses, compareAnalyses, compareSemanticAnalyses } from '../api';
import type { AnalysisResponse, AggregateCompareResponse, SemanticCompareResponse } from '../api';
import { BarChart2, Loader2, AlertCircle } from 'lucide-react';
import { tr, useLanguage } from '../i18n';

export default function Compare() {
  const { language } = useLanguage();
  const [analyses, setAnalyses] = useState<AnalysisResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [compareResult, setCompareResult] = useState<AggregateCompareResponse | null>(null);
  const [semanticResult, setSemanticResult] = useState<SemanticCompareResponse | null>(null);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState('');
  const [semanticError, setSemanticError] = useState('');
  const [matchFilter, setMatchFilter] = useState<'all' | 'high'>('all');

  useEffect(() => {
    fetchAnalyses();
  }, []);

  const fetchAnalyses = async () => {
    try {
      const data = await listAnalyses(50, 0); // fetch more for comparison
      setAnalyses(data.items.filter(a => a.status === 'completed' && a.result));
    } catch (err) {
      console.error(err);
      setError(tr('Could not load analysis history. Check that the backend is running at http://localhost:8000.', language));
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (id: number) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleCompare = async () => {
    const selected = analyses.filter(a => selectedIds.includes(a.analysis_id));
    const hasChinese = selected.some(a => a.result?.language === 'zh');
    const hasKazakh = selected.some(a => a.result?.language === 'kk');
    if (!hasChinese || !hasKazakh) {
      setError(tr('Select at least one Chinese (zh) and one Kazakh (kk) analysis.', language));
      return;
    }
    setError('');
    setCompareResult(null);
    setSemanticResult(null);
    setSemanticError('');
    setComparing(true);
    try {
      const res = await compareAnalyses(selectedIds);
      setCompareResult(res);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || tr('Failed to compare.', language));
      setComparing(false);
      return;
    }
    try {
      const semantic = await compareSemanticAnalyses(selectedIds);
      setSemanticResult(semantic);
    } catch (err: any) {
      console.warn('Semantic comparison is unavailable', err);
      setSemanticError(tr('Semantic comparison is temporarily unavailable; aggregate comparison is still shown.', language));
    } finally {
      setComparing(false);
    }
  };

  const selectedMetaphors = useMemo(
    () => analyses.filter(a => selectedIds.includes(a.analysis_id)).flatMap(a =>
      (a.result?.metaphors ?? []).map(m => ({ ...m, language: a.result?.language ?? '' }))
    ),
    [analyses, selectedIds]
  );

  const typeRows = useMemo(() => {
    const labels = Array.from(new Set(selectedMetaphors.map(m => m.label)));
    return labels.map(label => ({
      label,
      zh: selectedMetaphors.filter(m => m.language === 'zh' && m.label === label).length,
      kk: selectedMetaphors.filter(m => m.language === 'kk' && m.label === label).length,
    }));
  }, [selectedMetaphors]);

  const sourceDomains = useMemo(() => {
    const zh = new Set(selectedMetaphors.filter(m => m.language === 'zh').map(m => m.source_domain));
    const kk = new Set(selectedMetaphors.filter(m => m.language === 'kk').map(m => m.source_domain));
    return {
      common: Array.from(zh).filter(domain => kk.has(domain)),
      zhOnly: Array.from(zh).filter(domain => !kk.has(domain)),
      kkOnly: Array.from(kk).filter(domain => !zh.has(domain)),
    };
  }, [selectedMetaphors]);

  const filteredMatches = semanticResult?.matches.filter(match => matchFilter === 'all' || match.similarity >= 0.7) ?? [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
        <BarChart2 className="w-6 h-6 text-indigo-600" />
        {tr('Compare Analyses', language)}
      </h1>
      <p className="text-gray-600">
        {tr('Select at least one completed Chinese (zh) and one Kazakh (kk) analysis to compare metaphorical patterns.', language)}
      </p>

      {error && (
        <div className="p-4 bg-red-50 text-red-700 rounded-md border border-red-200 flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          {typeof error === 'string' ? error : JSON.stringify(error)}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-1 bg-white p-4 rounded-lg shadow-sm border border-gray-200 h-[600px] flex flex-col">
          <h2 className="font-semibold text-gray-800 mb-4">{tr('Completed Analyses', language)}</h2>
          {loading ? (
            <div className="flex justify-center p-4"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
          ) : (
            <div className="overflow-y-auto flex-1 space-y-2 pr-2">
              {analyses.map(a => (
                <label key={a.analysis_id} className="flex items-start gap-3 p-3 rounded border border-gray-200 hover:bg-gray-50 cursor-pointer">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-600"
                    checked={selectedIds.includes(a.analysis_id)}
                    onChange={() => toggleSelect(a.analysis_id)}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 truncate">
                      #{a.analysis_id} {a.source_name ? `- ${a.source_name}` : ''}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Lang: <span className="font-bold">{a.result?.language}</span> | Metaphors: {a.result?.metaphors.length}
                    </div>
                  </div>
                </label>
              ))}
              {analyses.length === 0 && <div className="text-sm text-gray-500">{tr('No completed analyses found.', language)}</div>}
            </div>
          )}
          <p className="mt-3 text-xs text-gray-500">
            {tr('Select at least one Chinese and one Kazakh analysis.', language)}
          </p>
          <button
            onClick={handleCompare}
            disabled={comparing || !analyses.some(a => selectedIds.includes(a.analysis_id) && a.result?.language === 'zh') || !analyses.some(a => selectedIds.includes(a.analysis_id) && a.result?.language === 'kk')}
            className="mt-4 w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50"
          >
            {comparing ? <Loader2 className="w-4 h-4 animate-spin" /> : tr('Compare Selected', language)}
          </button>
        </div>

        <div className="lg:col-span-2">
          {compareResult ? (
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
              <h2 className="text-xl font-bold mb-4">{tr('Comparison Results', language)}</h2>
              <p className="text-sm text-gray-500 mb-6 bg-blue-50 p-3 rounded">{compareResult.note}</p>

              <section className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
                {(['zh', 'kk'] as const).map(lang => {
                  const group = compareResult.languages[lang];
                  const items = selectedMetaphors.filter(m => m.language === lang);
                  const average = items.length ? items.reduce((sum, item) => sum + item.confidence, 0) / items.length : 0;
                  return (
                    <div key={lang} className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                      <p className="text-xs uppercase tracking-wide text-gray-500">{lang === 'zh' ? tr('Chinese', language) : tr('Kazakh', language)}</p>
                      <p className="mt-1 text-2xl font-bold text-gray-900">{group?.metaphor_count ?? 0}</p>
                      <p className="text-xs text-gray-500">{tr('metaphors', language)} · {tr('Average confidence', language)} {(average * 100).toFixed(0)}%</p>
                    </div>
                  );
                })}
                <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4">
                  <p className="text-xs uppercase tracking-wide text-indigo-600">{tr('Common source domains', language)}</p>
                  <p className="mt-1 text-2xl font-bold text-indigo-900">{sourceDomains.common.length}</p>
                  <p className="text-xs text-indigo-700">{tr('shared image categories', language)}</p>
                </div>
              </section>

              <section className="mb-6 rounded-lg border border-gray-200 p-4">
                <h3 className="font-semibold text-gray-900 mb-3">{tr('Type comparison', language)}</h3>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead><tr className="border-b text-left text-gray-500"><th className="py-2">{tr('Type', language)}</th><th className="py-2">{tr('Chinese', language)}</th><th className="py-2">{tr('Kazakh', language)}</th></tr></thead>
                    <tbody>{typeRows.map(row => <tr key={row.label} className="border-b last:border-0"><td className="py-2 font-medium">{tr(row.label, language)}</td><td className="py-2">{row.zh}</td><td className="py-2">{row.kk}</td></tr>)}</tbody>
                  </table>
                </div>
              </section>

              <section className="mb-6 rounded-lg border border-gray-200 p-4">
                <h3 className="font-semibold text-gray-900 mb-3">{tr('Cultural image comparison', language)}</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                  <div><p className="font-medium text-gray-700">{tr('Common', language)}</p><p className="text-gray-500 mt-1">{sourceDomains.common.map(x => tr(x, language)).join(', ') || '—'}</p></div>
                  <div><p className="font-medium text-gray-700">{tr('Chinese only', language)}</p><p className="text-gray-500 mt-1">{sourceDomains.zhOnly.map(x => tr(x, language)).join(', ') || '—'}</p></div>
                  <div><p className="font-medium text-gray-700">{tr('Kazakh only', language)}</p><p className="text-gray-500 mt-1">{sourceDomains.kkOnly.map(x => tr(x, language)).join(', ') || '—'}</p></div>
                </div>
              </section>

              {semanticResult && (
                <section className="mb-6 rounded-lg border border-indigo-100 bg-indigo-50/50 p-4">
                    <h3 className="font-semibold text-gray-900">{tr('Cross-language metaphor candidates', language)}</h3>
                  <p className="mt-1 text-xs text-gray-500">
                    {semanticResult.model_version} · {tr('Similarity ranks candidates; it does not prove cultural equivalence.', language)}
                  </p>
                  <div className="mt-3 flex gap-2">
                    <button onClick={() => setMatchFilter('all')} className={`rounded px-2 py-1 text-xs ${matchFilter === 'all' ? 'bg-indigo-600 text-white' : 'bg-white text-gray-600'}`}>{tr('All matches', language)}</button>
                    <button onClick={() => setMatchFilter('high')} className={`rounded px-2 py-1 text-xs ${matchFilter === 'high' ? 'bg-indigo-600 text-white' : 'bg-white text-gray-600'}`}>{tr('High similarity', language)}</button>
                  </div>
                  {semanticResult.warnings.map(warning => (
                    <p key={warning} className="mt-2 text-sm text-amber-700">{warning}</p>
                  ))}
                  {filteredMatches.length > 0 ? (
                    <ul className="mt-3 space-y-2">
                      {filteredMatches.map(match => {
                        const query = analyses.flatMap(a => (a.result?.metaphors ?? []).map((m, index) => ({
                          id: `${a.analysis_id}:${index}`, text: m.text, language: a.result?.language,
                        }))).find(item => item.id === match.query_id);
                        const candidate = analyses.flatMap(a => (a.result?.metaphors ?? []).map((m, index) => ({
                          id: `${a.analysis_id}:${index}`, text: m.text, language: a.result?.language,
                        }))).find(item => item.id === match.candidate_id);
                        return (
                          <li key={`${match.query_id}-${match.candidate_id}`} className="flex flex-wrap justify-between gap-2 rounded bg-white px-3 py-2 text-sm">
                            <span>{query?.language}: “{query?.text ?? match.query_id}” ↔ {candidate?.language}: “{candidate?.text ?? match.candidate_id}”</span>
                            <span className="font-mono text-indigo-700">cosine {match.similarity.toFixed(3)} · #{match.rank}</span>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="mt-3 text-sm text-gray-600">{tr('No cross-language candidates to display.', language)}</p>
                  )}
                </section>
              )}
              {semanticError && <p className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">{semanticError}</p>}
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {Object.entries(compareResult.languages).map(([lang, data]: [string, any]) => (
                  <div key={lang} className="space-y-4">
                    <h3 className="text-lg font-semibold bg-gray-100 p-2 rounded text-center uppercase tracking-wider">
                      {lang === 'zh' ? tr('Chinese', language) : lang === 'kk' ? tr('Kazakh', language) : lang}
                    </h3>
                    <div className="flex justify-between text-sm text-gray-600 px-2">
                      <span>{tr('Analyses', language)}: <strong>{data.analysis_count}</strong></span>
                      <span>{tr('Total Metaphors', language)}: <strong>{data.metaphor_count}</strong></span>
                    </div>
                    
                    <div className="border border-gray-200 rounded p-4">
                      <h4 className="text-sm font-bold text-gray-700 mb-3 border-b pb-1">{tr('Top Sources', language)}</h4>
                      <ul className="space-y-1">
                        {Object.entries(data.by_source_domain)
                          .sort(([, a], [, b]) => (b as number) - (a as number))
                          .slice(0, 5)
                          .map(([domain, count]) => (
                            <li key={domain} className="flex justify-between text-sm">
                              <span className="text-gray-700">{domain}</span>
                              <span className="font-mono bg-gray-100 px-1.5 rounded">{count as number}</span>
                            </li>
                        ))}
                      </ul>
                    </div>

                    <div className="border border-gray-200 rounded p-4">
                      <h4 className="text-sm font-bold text-gray-700 mb-3 border-b pb-1">{tr('Top Targets', language)}</h4>
                      <ul className="space-y-1">
                        {Object.entries(data.by_target_domain)
                          .sort(([, a], [, b]) => (b as number) - (a as number))
                          .slice(0, 5)
                          .map(([domain, count]) => (
                            <li key={domain} className="flex justify-between text-sm">
                              <span className="text-gray-700">{domain}</span>
                              <span className="font-mono bg-gray-100 px-1.5 rounded">{count as number}</span>
                            </li>
                        ))}
                      </ul>
                    </div>

                    <div className="border border-gray-200 rounded p-4">
                      <h4 className="text-sm font-bold text-gray-700 mb-3 border-b pb-1">{tr('Types', language)}</h4>
                      <ul className="space-y-1">
                        {Object.entries(data.by_label)
                          .sort(([, a], [, b]) => (b as number) - (a as number))
                          .map(([label, count]) => (
                            <li key={label} className="flex justify-between text-sm">
                              <span className="text-gray-700 capitalize">{label}</span>
                              <span className="font-mono bg-gray-100 px-1.5 rounded">{count as number}</span>
                            </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-gray-400 p-8 border-2 border-dashed border-gray-200 rounded-lg">
              <BarChart2 className="w-12 h-12 mb-4 text-gray-300" />
              <p>{tr('Select analyses and click compare to see results here.', language)}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

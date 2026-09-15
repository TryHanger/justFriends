import { useState, useEffect } from 'react';
import { listAnalyses, compareAnalyses } from '../api';
import type { AnalysisResponse } from '../api';
import { BarChart2, Loader2, AlertCircle } from 'lucide-react';

export default function Compare() {
  const [analyses, setAnalyses] = useState<AnalysisResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [compareResult, setCompareResult] = useState<any>(null);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchAnalyses();
  }, []);

  const fetchAnalyses = async () => {
    try {
      const data = await listAnalyses(50, 0); // fetch more for comparison
      setAnalyses(data.filter(a => a.status === 'completed' && a.result));
    } catch (err) {
      console.error(err);
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
    if (selectedIds.length < 2) {
      setError('Please select at least two analyses.');
      return;
    }
    setError('');
    setComparing(true);
    try {
      const res = await compareAnalyses(selectedIds);
      setCompareResult(res);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Failed to compare.');
    } finally {
      setComparing(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
        <BarChart2 className="w-6 h-6 text-indigo-600" />
        Compare Analyses
      </h1>
      <p className="text-gray-600">
        Select at least one completed Chinese (zh) and one Kazakh (kk) analysis to compare metaphorical patterns.
      </p>

      {error && (
        <div className="p-4 bg-red-50 text-red-700 rounded-md border border-red-200 flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          {typeof error === 'string' ? error : JSON.stringify(error)}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-1 bg-white p-4 rounded-lg shadow-sm border border-gray-200 h-[600px] flex flex-col">
          <h2 className="font-semibold text-gray-800 mb-4">Completed Analyses</h2>
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
              {analyses.length === 0 && <div className="text-sm text-gray-500">No completed analyses found.</div>}
            </div>
          )}
          <button
            onClick={handleCompare}
            disabled={comparing || selectedIds.length < 2}
            className="mt-4 w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50"
          >
            {comparing ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Compare Selected'}
          </button>
        </div>

        <div className="lg:col-span-2">
          {compareResult ? (
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
              <h2 className="text-xl font-bold mb-4">Comparison Results</h2>
              <p className="text-sm text-gray-500 mb-6 bg-blue-50 p-3 rounded">{compareResult.note}</p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {Object.entries(compareResult.languages).map(([lang, data]: [string, any]) => (
                  <div key={lang} className="space-y-4">
                    <h3 className="text-lg font-semibold bg-gray-100 p-2 rounded text-center uppercase tracking-wider">
                      {lang === 'zh' ? 'Chinese' : lang === 'kk' ? 'Kazakh' : lang}
                    </h3>
                    <div className="flex justify-between text-sm text-gray-600 px-2">
                      <span>Analyses: <strong>{data.analysis_count}</strong></span>
                      <span>Total Metaphors: <strong>{data.metaphor_count}</strong></span>
                    </div>
                    
                    <div className="border border-gray-200 rounded p-4">
                      <h4 className="text-sm font-bold text-gray-700 mb-3 border-b pb-1">Top Sources</h4>
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
                      <h4 className="text-sm font-bold text-gray-700 mb-3 border-b pb-1">Top Targets</h4>
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
                      <h4 className="text-sm font-bold text-gray-700 mb-3 border-b pb-1">Types</h4>
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
              <p>Select analyses and click compare to see results here.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

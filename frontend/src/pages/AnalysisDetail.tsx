import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Download, Loader2, AlertCircle, ChevronLeft } from 'lucide-react';
import { getAnalysis, getExportUrl } from '../api';
import type { AnalysisResponse } from '../api';
import { tr, useLanguage } from '../i18n';

export default function AnalysisDetail() {
  const { language } = useLanguage();
  const { id } = useParams<{ id: string }>();
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;

    const fetchStatus = async () => {
      if (!id) return;
      try {
        const data = await getAnalysis(parseInt(id, 10));
        setAnalysis(data);
        if (data.status === 'completed' || data.status === 'failed') {
          setLoading(false);
          clearInterval(interval);
        }
      } catch (err) {
        console.error(err);
        setLoading(false);
        clearInterval(interval);
      }
    };

    fetchStatus(); // initial fetch

    interval = setInterval(fetchStatus, 3000); // poll every 3 seconds

    return () => clearInterval(interval);
  }, [id]);

  if (loading && !analysis) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-600 mb-4" />
        <p className="text-gray-500">{tr('Loading analysis...', language)}</p>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="text-center p-8 bg-red-50 rounded-lg text-red-600">
        <AlertCircle className="w-8 h-8 mx-auto mb-2" />
        <p>{tr('Analysis not found or error loading it.', language)}</p>
        <Link to="/" className="text-indigo-600 hover:underline mt-4 inline-block">{tr('Go back', language)}</Link>
      </div>
    );
  }

  const isComplete = analysis.status === 'completed';
  const isFailed = analysis.status === 'failed';
  const metaphors = analysis.result?.metaphors || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/" className="p-2 bg-white rounded-full border border-gray-200 hover:bg-gray-50 text-gray-500">
          <ChevronLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">{tr('Analysis #', language)}{analysis.analysis_id}</h1>
        <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
          isComplete ? 'bg-green-100 text-green-800' :
          isFailed ? 'bg-red-100 text-red-800' :
          'bg-yellow-100 text-yellow-800'
        }`}>
          {tr(analysis.status, language)}
        </span>
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">{tr('Metadata', language)}</h3>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-4">
          <div>
            <dt className="text-sm font-medium text-gray-500">{tr('Source', language)}</dt>
            <dd className="mt-1 text-sm text-gray-900">{analysis.source_name || tr('Text Input', language)}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">{tr('Created At', language)}</dt>
            <dd className="mt-1 text-sm text-gray-900">{new Date(analysis.created_at).toLocaleString()}</dd>
          </div>
          {isComplete && analysis.result && (
            <>
              <div>
                <dt className="text-sm font-medium text-gray-500">{tr('Language', language)}</dt>
                <dd className="mt-1 text-sm text-gray-900">{analysis.result.language === 'zh' ? tr('Chinese (zh)', language) : analysis.result.language === 'kk' ? tr('Kazakh (kk)', language) : analysis.result.language}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">{tr('Model Version', language)}</dt>
                <dd className="mt-1 text-sm text-gray-900">{analysis.result.model_version}</dd>
              </div>
            </>
          )}
        </dl>
      </div>

      {!isComplete && !isFailed && (
        <div className="flex flex-col items-center justify-center p-12 bg-white rounded-lg shadow-sm border border-gray-200">
          <Loader2 className="w-10 h-10 animate-spin text-indigo-600 mb-4" />
          <p className="text-gray-600 font-medium text-lg">{tr('Analysis in progress...', language)}</p>
          <p className="text-sm text-gray-400 mt-2">{tr("This may take a few moments. We'll automatically refresh.", language)}</p>
        </div>
      )}

      {isFailed && (
        <div className="bg-red-50 p-6 rounded-lg border border-red-200">
          <h3 className="text-lg font-medium text-red-800 mb-2 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            {tr('Analysis Failed', language)}
          </h3>
          <p className="text-red-600">{analysis.error || tr('An unknown error occurred during analysis.', language)}</p>
        </div>
      )}

      {isComplete && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-bold text-gray-900">{tr('Found Metaphors', language)} ({metaphors.length})</h2>
            <div className="flex gap-2">
              <a
                href={getExportUrl(analysis.analysis_id, 'json')}
                className="inline-flex items-center gap-2 px-3 py-1.5 border border-gray-300 rounded text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
              >
                <Download className="w-4 h-4" /> JSON
              </a>
              <a
                href={getExportUrl(analysis.analysis_id, 'csv')}
                className="inline-flex items-center gap-2 px-3 py-1.5 border border-gray-300 rounded text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
              >
                <Download className="w-4 h-4" /> CSV
              </a>
            </div>
          </div>
          
          <div className="grid gap-4 md:grid-cols-2">
            {metaphors.map((m, idx) => (
              <div key={idx} className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                <div className="flex justify-between items-start mb-2">
                  <span className="inline-flex items-center rounded-md bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-700/10">
                    {tr(m.label, language)}
                  </span>
                  <span className="text-xs text-gray-500 font-mono">
                    {tr('Conf:', language)} {(m.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <blockquote className="text-lg font-serif mb-4 border-l-4 border-indigo-200 pl-3 py-1 text-gray-800 bg-gray-50">
                  "{m.text}"
                </blockquote>
                <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm mb-3">
                  <div>
                    <span className="text-gray-500">{tr('Source:', language)}</span> <span className="font-medium text-gray-900">{tr(m.source_domain, language)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">{tr('Target:', language)}</span> <span className="font-medium text-gray-900">{tr(m.target_domain, language)}</span>
                  </div>
                </div>
                <p className="text-sm text-gray-600 bg-gray-50 p-2 rounded">
                  {m.rationale}
                </p>
              </div>
            ))}
            {metaphors.length === 0 && (
              <div className="col-span-2 text-center p-8 bg-gray-50 rounded-lg text-gray-500">
                {tr('No metaphors detected in this document.', language)}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

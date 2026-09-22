import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, FileText, Plus, Loader2 } from 'lucide-react';
import { listAnalyses, submitText, submitFile } from '../api';
import type { AnalysisResponse } from '../api';
import { tr, useLanguage } from '../i18n';

export default function Dashboard() {
  const { language: uiLanguage } = useLanguage();
  const navigate = useNavigate();
  const [analyses, setAnalyses] = useState<AnalysisResponse[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState('');
  
  const [text, setText] = useState('');
  const [analysisLanguage, setAnalysisLanguage] = useState('auto');
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchAnalyses();
  }, []);

  const fetchAnalyses = async () => {
    try {
      setLoadingList(true);
      const data = await listAnalyses();
      setAnalyses(data.items);
    } catch (err) {
      console.error(err);
      setListError(tr('Could not load analysis history. Check that the backend is running at http://localhost:8000.', uiLanguage));
    } finally {
      setLoadingList(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text && !file) {
      setError(tr('Please provide text or select a file.', uiLanguage));
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      let res;
      if (file) {
        res = await submitFile(file, analysisLanguage);
      } else {
        res = await submitText(text, analysisLanguage);
      }
      navigate(`/analyses/${res.analysis_id}`);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || tr('Failed to submit analysis.', uiLanguage));
      setSubmitting(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setText(''); // Clear text if file is selected
    }
  };

  const clearFile = () => {
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
      <div className="md:col-span-1 space-y-6">
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
            <Plus className="w-5 h-5 text-indigo-600" />
            {tr('New Analysis', uiLanguage)}
          </h2>
          {error && <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-md text-sm">{error}</div>}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{tr('Language', uiLanguage)}</label>
              <select
                value={analysisLanguage}
                onChange={(e) => setAnalysisLanguage(e.target.value)}
                className="w-full border-gray-300 rounded-md shadow-sm focus:border-indigo-500 focus:ring-indigo-500 p-2 border"
              >
                <option value="auto">{tr('Auto-detect', uiLanguage)}</option>
                <option value="zh">{tr('Chinese (zh)', uiLanguage)}</option>
                <option value="kk">{tr('Kazakh (kk)', uiLanguage)}</option>
              </select>
            </div>
            
            {!file ? (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{tr('Poem Text', uiLanguage)}</label>
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  className="w-full border-gray-300 rounded-md shadow-sm focus:border-indigo-500 focus:ring-indigo-500 p-2 border min-h-[150px]"
                  placeholder={tr('Paste poem text here...', uiLanguage)}
                />
                <div className="text-center text-sm text-gray-500 my-2">{tr('OR', uiLanguage)}</div>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
                >
                  <Upload className="w-4 h-4" />
                  {tr('Upload Document', uiLanguage)}
                </button>
              </div>
            ) : (
              <div className="p-4 border border-indigo-200 bg-indigo-50 rounded-md flex justify-between items-center">
                <div className="flex items-center gap-2 overflow-hidden">
                  <FileText className="w-5 h-5 text-indigo-600 flex-shrink-0" />
                  <span className="text-sm font-medium truncate">{file.name}</span>
                </div>
                <button type="button" onClick={clearFile} className="text-indigo-600 text-sm hover:underline ml-2">
                  {tr('Remove', uiLanguage)}
                </button>
              </div>
            )}
            
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              className="hidden"
              accept=".txt,.pdf,.docx"
            />
            
            <button
              type="submit"
              disabled={submitting || (!text && !file)}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="w-5 h-5 animate-spin" /> : tr('Analyze', uiLanguage)}
            </button>
          </form>
        </div>
      </div>

      <div className="md:col-span-2">
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <h2 className="text-xl font-bold mb-4">{tr('Recent Analyses', uiLanguage)}</h2>
          {loadingList ? (
            <div className="flex justify-center p-8">
              <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
            </div>
          ) : listError ? (
            <div className="text-center text-red-700 p-8 bg-red-50 rounded-lg">{listError}</div>
          ) : analyses.length === 0 ? (
            <div className="text-center text-gray-500 p-8 border-2 border-dashed border-gray-200 rounded-lg">
              {tr('No analyses yet. Submit your first poem!', uiLanguage)}
            </div>
          ) : (
            <div className="overflow-hidden shadow ring-1 ring-black ring-opacity-5 md:rounded-lg">
              <table className="min-w-full divide-y divide-gray-300">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900">{tr('ID', uiLanguage)}</th>
                    <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">{tr('Source', uiLanguage)}</th>
                    <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">{tr('Language', uiLanguage)}</th>
                    <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">{tr('Status', uiLanguage)}</th>
                    <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">{tr('Date', uiLanguage)}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 bg-white">
                  {analyses.map((a) => (
                    <tr
                      key={a.analysis_id}
                      onClick={() => navigate(`/analyses/${a.analysis_id}`)}
                      className="cursor-pointer hover:bg-gray-50"
                    >
                      <td className="whitespace-nowrap py-4 pl-4 pr-3 text-sm font-medium text-gray-900">
                        #{a.analysis_id}
                      </td>
                      <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500 truncate max-w-[150px]">
                        {a.source_name || tr('Text input', uiLanguage)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                        {a.result?.language || '-'}
                      </td>
                      <td className="whitespace-nowrap px-3 py-4 text-sm">
                        <span className={`inline-flex rounded-full px-2 text-xs font-semibold leading-5 ${
                          a.status === 'completed' ? 'bg-green-100 text-green-800' :
                          a.status === 'failed' ? 'bg-red-100 text-red-800' :
                          'bg-yellow-100 text-yellow-800'
                        }`}>
                          {uiLanguage === 'ru' ? ({ completed: 'Завершён', failed: 'Ошибка', pending: 'В очереди', processing: 'Выполняется' }[a.status] || a.status) : a.status}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                        {new Date(a.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

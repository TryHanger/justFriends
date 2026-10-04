import { useState, useEffect, useRef } from 'react';
import { getStandardsReference, getLifecycleState, runQualityChecks } from '../api';
import type { StandardInfo, LifecycleState, QualityReport } from '../api';
import { getApiErrorMessage } from '../apiErrors';
import { BookOpen, GitCommit, ShieldCheck, Loader2, PlayCircle, CheckCircle, XCircle, AlertCircle } from 'lucide-react';

export default function Standards() {
  const [activeTab, setActiveTab] = useState<'reference' | 'lifecycle' | 'quality'>('reference');
  
  // Reference State
  const [standards, setStandards] = useState<StandardInfo[]>([]);
  const [loadingRef, setLoadingRef] = useState(true);
  const [referenceError, setReferenceError] = useState<string | null>(null);

  // Lifecycle State
  const [lifecycle, setLifecycle] = useState<LifecycleState | null>(null);
  const [loadingLife, setLoadingLife] = useState(false);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);
  const lifecycleRequest = useRef(0);

  // Quality State
  const [qualityReport, setQualityReport] = useState<QualityReport | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);
  const [runningQuality, setRunningQuality] = useState(false);

  useEffect(() => {
    getStandardsReference()
      .then(setStandards)
      .catch(e => setReferenceError(getApiErrorMessage(e, 'Could not load the reference catalog.')))
      .finally(() => setLoadingRef(false));
  }, []);

  const loadReference = async () => {
    setLoadingRef(true);
    setReferenceError(null);
    try {
      setStandards(await getStandardsReference());
    } catch (e) {
      setReferenceError(getApiErrorMessage(e, 'Could not load the reference catalog.'));
    } finally {
      setLoadingRef(false);
    }
  };

  const loadLifecycle = async () => {
    const request = ++lifecycleRequest.current;
    setLoadingLife(true);
    setLifecycleError(null);
    setLifecycle(null);
    try {
      const state = await getLifecycleState();
      if (request === lifecycleRequest.current) setLifecycle(state);
    } catch (e) {
      if (request === lifecycleRequest.current) {
        setLifecycleError(getApiErrorMessage(e, 'Could not load lifecycle evidence.'));
      }
    } finally {
      if (request === lifecycleRequest.current) setLoadingLife(false);
    }
  };

  const handleRunQuality = async () => {
    setQualityReport(null);
    setQualityError(null);
    setRunningQuality(true);
    try {
      const report = await runQualityChecks();
      setQualityReport(report);
    } catch (e) {
      setQualityError(getApiErrorMessage(e, 'Could not run automated tests.'));
    } finally {
      setRunningQuality(false);
      void loadLifecycle();
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-gray-900">ISO Standards & Quality Control</h1>
        <div className="flex space-x-1 rounded-lg bg-gray-100 p-1">
          <button
            onClick={() => { setActiveTab('reference'); if (referenceError) void loadReference(); }}
            className={`flex items-center px-3 py-1.5 text-sm font-medium rounded-md ${activeTab === 'reference' ? 'bg-white shadow text-indigo-700' : 'text-gray-500 hover:text-gray-700'}`}
          >
            <BookOpen className="w-4 h-4 mr-2" /> Reference
          </button>
          <button
            onClick={() => { setActiveTab('lifecycle'); void loadLifecycle(); }}
            className={`flex items-center px-3 py-1.5 text-sm font-medium rounded-md ${activeTab === 'lifecycle' ? 'bg-white shadow text-indigo-700' : 'text-gray-500 hover:text-gray-700'}`}
          >
            <GitCommit className="w-4 h-4 mr-2" /> Lifecycle
          </button>
          <button
            onClick={() => setActiveTab('quality')}
            className={`flex items-center px-3 py-1.5 text-sm font-medium rounded-md ${activeTab === 'quality' ? 'bg-white shadow text-indigo-700' : 'text-gray-500 hover:text-gray-700'}`}
          >
            <ShieldCheck className="w-4 h-4 mr-2" /> Quality
          </button>
        </div>
      </div>

      {activeTab === 'reference' && (
        <div className="bg-white shadow-sm border border-gray-200 rounded-lg overflow-hidden">
          <div className="p-4 border-b border-gray-200 bg-gray-50">
            <h2 className="text-lg font-semibold text-gray-800">ISO/IEC/IEEE Standards Directory</h2>
            <p className="text-sm text-gray-500">Reference catalog of standards relevant to software projects.</p>
          </div>
          {loadingRef ? (
            <div className="p-8 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
          ) : referenceError ? (
            <div className="p-6"><p role="alert" className="text-red-700 mb-3">{referenceError}</p><button onClick={loadReference} className="text-indigo-700 underline">Retry reference</button></div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Designation</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Title</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Domain</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {standards.map((s, idx) => (
                    <tr key={idx} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="font-medium text-gray-900">{s.designation}</div>
                        <div className="text-xs text-gray-500">{s.organization}</div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm text-gray-900">{s.title}</div>
                        <div className="text-xs text-gray-500 mt-1 line-clamp-1" title={s.purpose}>{s.purpose}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          {s.domain}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'lifecycle' && (
        <div className="space-y-6">
          <div className="bg-white shadow-sm border border-gray-200 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-800 mb-2">Project lifecycle evidence</h2>
            <p className="text-sm text-gray-600 mb-6">Repository evidence for manual review. File presence and test results do not establish ISO conformance.</p>
            
            {loadingLife ? (
              <div className="flex justify-center p-8"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
            ) : lifecycleError ? (
              <div><p role="alert" className="text-red-700 mb-3">{lifecycleError}</p><button onClick={loadLifecycle} className="text-indigo-700 underline">Retry lifecycle</button></div>
            ) : lifecycle ? (
              <div className="space-y-6">
                <p className="text-sm text-gray-600">Last checked: {lifecycle.last_checked_at ? new Date(lifecycle.last_checked_at).toLocaleString() : 'Not run in this server process'}</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <h3 className="text-sm font-bold text-gray-500 uppercase mb-3">Process Map</h3>
                    <div className="space-y-3">
                      {lifecycle.processes.map((p, idx) => (
                        <div key={idx} className="flex items-center p-3 rounded-md border border-gray-200 bg-gray-50">
                          <div className="flex-1">
                            <div className="font-medium text-gray-900">{p.name}</div>
                            <div className="text-xs text-gray-500">Assigned: {p.responsible}</div>
                            {p.details && <div className="text-xs text-gray-600 mt-1">{p.details}</div>}
                            {p.evidence && p.evidence.length > 0 && <div className="text-xs text-gray-600 mt-1">Evidence: {p.evidence.join(', ')}</div>}
                          </div>
                          <div>
                            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full
                              ${p.status === 'evidence_found' || p.status === 'PASS' ? 'bg-green-100 text-green-800' :
                                p.status === 'missing' || p.status === 'FAIL' || p.status === 'unavailable' ? 'bg-red-100 text-red-800' :
                                p.status === 'INCOMPLETE' || p.status === 'running' ? 'bg-yellow-100 text-yellow-800' :
                                'bg-gray-100 text-gray-800'}`}>
                              {p.status.replace(/_/g, ' ').toUpperCase()}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-gray-500 uppercase mb-3">Assessment</h3>
                    <div className="bg-blue-50 border border-blue-200 rounded-md p-4 mb-4">
                      <div className="text-sm font-medium text-blue-800 mb-1">Overall Readiness</div>
                      <div className="text-xl font-bold text-blue-900">{lifecycle.readiness}</div>
                    </div>
                    {lifecycle.issues.length > 0 && (
                      <div className="bg-red-50 border border-red-200 rounded-md p-4">
                        <div className="text-sm font-medium text-red-800 mb-2">Identified Issues</div>
                        <ul className="list-disc pl-5 space-y-1 text-sm text-red-700">
                          {lifecycle.issues.map((issue, idx) => (
                            <li key={idx}>{issue}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {activeTab === 'quality' && (
        <div className="space-y-6">
          <div className="bg-white shadow-sm border border-gray-200 rounded-lg p-6">
            <div className="flex justify-between items-start mb-6">
              <div>
                <h2 className="text-lg font-semibold text-gray-800">Automated Test Results</h2>
                <p className="text-sm text-gray-600">Runs the project's Python tests and reports measured results.</p>
              </div>
              <button
                onClick={handleRunQuality}
                disabled={runningQuality}
                className="flex items-center px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50"
              >
                {runningQuality ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <PlayCircle className="w-4 h-4 mr-2" />}
                {runningQuality ? 'Running Tests...' : 'Run Automated Tests'}
              </button>
            </div>

            {qualityError && <p role="alert" className="mb-6 text-sm text-red-700">{qualityError}</p>}
            {qualityReport ? (
              <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4">
                <div className={`p-4 rounded-md border flex items-center gap-4
                  ${qualityReport.overall_status === 'PASS' ? 'bg-green-50 border-green-200 text-green-800' : qualityReport.overall_status === 'INCOMPLETE' ? 'bg-amber-50 border-amber-200 text-amber-800' : 'bg-red-50 border-red-200 text-red-800'}`}>
                  {qualityReport.overall_status === 'PASS' ? <CheckCircle className="w-8 h-8" /> : qualityReport.overall_status === 'INCOMPLETE' ? <AlertCircle className="w-8 h-8" /> : <XCircle className="w-8 h-8" />}
                  <div>
                    <h3 className="font-bold text-lg">Automated tests: {qualityReport.overall_status}</h3>
                    <p className="text-sm opacity-90">{qualityReport.passed_tests} out of {qualityReport.total_tests} test cases passed. {qualityReport.overall_status === 'INCOMPLETE' ? 'Some tests were skipped.' : ''}</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4">
                  {qualityReport.metrics.map((m, idx) => (
                    <div key={idx} className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                      <div className="flex justify-between items-center mb-2">
                        <span className="font-medium text-gray-900">{m.characteristic}</span>
                        <span
                          role="img"
                          aria-label={qualityReport.overall_status === 'PASS' ? 'Tests passed' : qualityReport.overall_status === 'INCOMPLETE' ? 'Tests incomplete' : 'Tests failed'}
                          className={qualityReport.overall_status === 'PASS' ? 'text-green-500' : qualityReport.overall_status === 'INCOMPLETE' ? 'text-amber-500' : 'text-red-500'}
                        >
                          {qualityReport.overall_status === 'PASS' ? <CheckCircle className="w-5 h-5" /> : qualityReport.overall_status === 'INCOMPLETE' ? <AlertCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
                        </span>
                      </div>
                      <div className="text-3xl font-bold text-indigo-600 mb-2">{m.score.toFixed(1)}%</div>
                      <div className="text-xs text-gray-500 h-8 line-clamp-2">{m.details}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : !runningQuality ? (
              <div className="text-center p-12 border-2 border-dashed border-gray-200 rounded-lg text-gray-500">
                Run automated tests to view the measured test pass rate.
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

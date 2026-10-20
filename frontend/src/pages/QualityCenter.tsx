import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { compareCheckRuns, getCheckRun, listCheckRuns, listProjectChecks, startCheckRun } from '../api';
import type { CheckComparison, CheckRun, CheckStatus, ProjectCheck } from '../api';
import { getApiErrorMessage } from '../apiErrors';
import { useLanguage } from '../i18n';
import { characteristicName, testPurpose } from './qualityPresentation';

const statusColor: Record<CheckStatus, string> = {
  queued: 'bg-sky-100 text-sky-800', running: 'bg-sky-100 text-sky-800',
  passed: 'bg-emerald-100 text-emerald-800', failed: 'bg-rose-100 text-rose-800',
  skipped: 'bg-amber-100 text-amber-800', unavailable: 'bg-slate-100 text-slate-700',
  timeout: 'bg-rose-100 text-rose-800', error: 'bg-rose-100 text-rose-800',
  interrupted: 'bg-amber-100 text-amber-800',
};
const terminal = new Set<CheckStatus>(['passed', 'failed', 'skipped', 'unavailable', 'timeout', 'error', 'interrupted']);
const labels: Record<CheckStatus, [string, string]> = {
  queued: ['В очереди', 'Queued'], running: ['Выполняется', 'Running'],
  passed: ['Успешно', 'Passed'], failed: ['Ошибка проверки', 'Failed'],
  skipped: ['Есть пропуски', 'Skipped'], unavailable: ['Недоступно', 'Unavailable'],
  timeout: ['Превышено время', 'Timeout'], error: ['Ошибка запуска', 'Error'],
  interrupted: ['Прервано', 'Interrupted'],
};
const descriptions: Record<string, [string, string]> = {
  'backend-tests': ['Проверяет поведение API и контрактов; не измеряет качество NLP-модели.', 'Checks API behavior and contracts; does not measure NLP model quality.'],
  'python-static': ['Ищет ошибки и нарушения выбранных правил Python; не доказывает отсутствие дефектов.', 'Checks selected Python rules; does not prove absence of defects.'],
  'frontend-tests': ['Проверяет компоненты и обмен с API; не заменяет пользовательское тестирование.', 'Checks components and API transport; does not replace user testing.'],
  typescript: ['Проверяет типы интерфейса; не доказывает корректность сценариев.', 'Checks frontend types; does not prove workflows are correct.'],
  'frontend-build': ['Подтверждает сборку интерфейса; не доказывает работу в браузерах.', 'Confirms frontend build; does not prove browser compatibility.'],
};
const requirementEn: Record<string, string> = {
  'backend-tests': 'API contracts, input validation and persistence',
  'python-static': 'Python code rules from pyproject.toml',
  'frontend-tests': 'Frontend workflows and API transport',
  typescript: 'Frontend type contracts',
  'frontend-build': 'Deployable frontend build',
};
function savedRunLabel(run: CheckRun, en: boolean): string {
  const { passed = 0, failed = 0, skipped = 0 } = run.counts ?? {};
  if (run.status === 'skipped' && passed > 0 && failed === 0 && passed + skipped === (run.cases?.length ?? 0)) {
    return en ? `Tests passed, ${skipped} skipped` : `Тесты пройдены, ${skipped} пропущено`;
  }
  return labels[run.status]?.[en ? 1 : 0] ?? (en ? 'Unknown' : 'Нет данных');
}
function Badge({ status, en, run }: { status: CheckStatus | null; en: boolean; run?: CheckRun }) {
  return status ? <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusColor[status]}`}>{run ? savedRunLabel(run, en) : labels[status][en ? 1 : 0]}</span>
    : <span className="text-sm text-slate-500">{en ? 'Not checked' : 'Не проверено'}</span>;
}
const date = (value: string) => new Date(value).toLocaleString();

export default function QualityCenter({ initialRunId }: { initialRunId?: string | null }) {
  const { language } = useLanguage();
  const en = language === 'en';
  const [checks, setChecks] = useState<ProjectCheck[]>([]);
  const [history, setHistory] = useState<CheckRun[]>([]);
  const [selected, setSelected] = useState<CheckRun | null>(null);
  const [comparison, setComparison] = useState<CheckComparison | null>(null);
  const [first, setFirst] = useState('');
  const [second, setSecond] = useState('');
  const [kind, setKind] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      const available = await listProjectChecks();
      setChecks(available);
      setHistory(await listCheckRuns());
      setError('');
    } catch (cause) { setError(getApiErrorMessage(cause, en ? 'Could not load checks.' : 'Не удалось загрузить проверки.')); }
    finally { setLoading(false); }
  }, [en]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void refresh(); }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);
  useEffect(() => {
    if (!initialRunId) return;
    void getCheckRun(initialRunId).then(run => {
      setSelected(run);
      window.setTimeout(() => document.getElementById('quality-run-details')?.scrollIntoView?.({ behavior: 'smooth' }), 0);
    }).catch(cause => setError(getApiErrorMessage(cause, 'Не удалось открыть исходный запуск.')));
  }, [initialRunId]);
  useEffect(() => {
    if (!selected || terminal.has(selected.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await getCheckRun(selected.id);
        setSelected(next);
        if (terminal.has(next.status)) { setBusy(''); void refresh(); }
      } catch (cause) { setError(getApiErrorMessage(cause, en ? 'Status update failed.' : 'Не удалось обновить состояние.')); }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [selected, refresh, en]);

  const latest = history[0];
  const latestTests = useMemo(() => history.find(run => run.check_id === 'backend-tests' || run.check_id === 'frontend-tests'), [history]);
  const recent = useMemo(() => history.filter(run => (!kind || run.check_id === kind) && (!status || run.status === status)), [history, kind, status]);

  async function start(id: string) {
    setError(''); setBusy(id); setComparison(null);
    try { setSelected(await startCheckRun(id)); await refresh(); }
    catch (cause) { setBusy(''); setError(getApiErrorMessage(cause, en ? 'Could not start check.' : 'Не удалось запустить проверку.')); }
  }
  async function open(id: string) {
    try { setSelected(await getCheckRun(id)); setError(''); }
    catch (cause) { setError(getApiErrorMessage(cause, en ? 'Could not load result.' : 'Не удалось открыть результат.')); }
  }
  async function compare() {
    if (!first || !second || first === second) return;
    try { setComparison(await compareCheckRuns(first, second)); setError(''); }
    catch (cause) { setError(getApiErrorMessage(cause, en ? 'Could not compare runs.' : 'Не удалось сравнить запуски.')); }
  }

  return <div className="space-y-5">
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="text-xl font-bold">{en ? 'Project checks' : 'Проверки проекта'}</h2>
          <p className="mt-1 text-sm text-slate-600">{en ? 'Real tool results, saved history and run comparison.' : 'Реальные результаты инструментов, сохранённая история и сравнение запусков.'}</p></div>
        <span className="rounded-lg bg-indigo-50 px-3 py-2 text-xs text-indigo-800">{en ? 'Local trusted mode only' : 'Только доверенный локальный режим'}</span>
      </div>
    </section>

    {error && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</div>}

    <section className="grid gap-3 sm:grid-cols-4">
      <Metric title={en ? 'Last run' : 'Последний запуск'} value={latest ? <Badge status={latest.status} en={en} run={latest} /> : '—'} />
      <Metric title={en ? 'Passed tests' : 'Пройдено тестов'} value={latestTests?.counts.passed ?? '—'} />
      <Metric title={en ? 'Failed tests' : 'Ошибок тестов'} value={latestTests?.counts.failed ?? '—'} />
      <Metric title={en ? 'Skipped tests' : 'Пропущено тестов'} value={latestTests?.counts.skipped ?? '—'} />
    </section>
    <p className="text-xs text-slate-500">{latest ? `${en ? 'Last checked' : 'Последняя проверка'}: ${date(latest.created_at)}` : en ? 'No recorded checks yet.' : 'Сохранённых запусков пока нет.'} {en ? 'Static checks are excluded from test counts.' : 'Статические проверки не входят в счётчики тестов.'} {en ? 'Available tools' : 'Доступно инструментов'}: {checks.filter(check => check.available).length}/{checks.length || '—'}.</p>

    {loading && <p role="status" className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">{en ? 'Loading checks…' : 'Загрузка проверок…'}</p>}

    <section className="grid gap-3 md:grid-cols-2">
      {checks.map(check => <article key={check.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3"><div><h3 className="font-bold">{check.name}</h3><p className="mt-1 text-sm text-slate-600">{en ? descriptions[check.id]?.[1] : descriptions[check.id]?.[0]}</p></div><Badge status={check.last_status} en={en} run={history.find(run => run.id === check.last_run_id)} /></div>
        <p className="mt-3 text-xs text-slate-500">{check.available ? en ? 'Available' : 'Доступно' : en ? check.reason?.startsWith('Runner выключен') ? 'Runner is disabled; enable local mode.' : check.id.startsWith('frontend') || check.id === 'typescript' ? 'Node.js/npm or frontend dependencies are missing.' : check.id === 'python-static' ? 'Ruff is not installed.' : 'pytest or test files are missing.' : check.reason}</p>
        <p className="mt-1 text-xs text-slate-500">{en ? 'Project requirement' : 'Требование проекта'}: {en ? requirementEn[check.id] : check.project_requirement}</p>
        <p className="mt-1 text-xs text-slate-500">{en ? 'Quality link' : 'Связь с качеством'}: {check.characteristics.map(name => characteristicName(name, en)).join(', ')}. {en ? 'This is project evidence, not ISO certification.' : 'Это свидетельство проекта, а не сертификат ISO.'}</p>
        <p className="mt-1 text-xs text-slate-500">{en ? 'References' : 'Ориентиры'}: {check.standard_refs.join(', ')}</p>
        <div className="mt-4 flex gap-2"><button onClick={() => void start(check.id)} disabled={!check.available || !!busy}
          className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">{busy === check.id ? en ? 'Running…' : 'Выполняется…' : en ? 'Run' : 'Запустить'}</button>
          {check.last_run_id && <button onClick={() => void open(check.last_run_id!)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm">{en ? 'Details' : 'Подробности'}</button>}</div>
      </article>)}
    </section>

    {selected && <section id="quality-run-details" className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-lg font-bold">{en ? 'Run details' : 'Подробности запуска'} · {selected.check_id}</h3><Badge status={selected.status} en={en} run={selected} /></div>
      <p className="mt-2 text-sm text-slate-600">{savedRunLabel(selected, en)} · {date(selected.created_at)} · {selected.duration_seconds?.toFixed(2) ?? '—'} s</p>
      {selected.cases.length > 0 && <div className="mt-4 max-h-96 overflow-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">{en ? 'Test' : 'Тест'}</th><th className="p-2">{en ? 'Status' : 'Статус'}</th><th className="p-2">s</th></tr></thead><tbody>{selected.cases.map(test => <tr key={test.name} className="border-t align-top"><td className="p-2 text-xs"><strong className="block font-medium">{en ? test.name : testPurpose(test.name)}</strong><details className="mt-1"><summary className="cursor-pointer text-indigo-700">{en ? 'Test details' : 'Подробности теста'}</summary><p className="mt-1 break-all font-mono">{test.name}</p><p className="mt-1">{test.message || (en ? 'No additional message.' : 'Дополнительного сообщения нет.')}</p></details></td><td className="p-2">{test.status === 'passed' ? en ? 'Passed' : 'Успешно' : test.status === 'skipped' ? en ? 'Skipped' : 'Пропущен' : en ? 'Failed' : 'Ошибка'}</td><td className="p-2">{test.duration_seconds.toFixed(2)}</td></tr>)}</tbody></table></div>}
      {selected.diagnostics && <details className="mt-4"><summary className="cursor-pointer font-semibold">{en ? 'Tool diagnostics' : 'Диагностика инструмента'}</summary><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-slate-950 p-4 text-xs text-slate-100">{selected.diagnostics}</pre></details>}
      <p className="mt-4 text-xs text-slate-500">{en ? 'Tests demonstrate observed behavior in this run. They do not establish complete ISO compliance.' : 'Тесты показывают поведение в этом запуске, но не доказывают полное соответствие ISO.'}</p>
    </section>}

    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><h3 className="text-lg font-bold">{en ? 'Run history' : 'История проверок'}</h3>
      <div className="mt-3 flex flex-wrap gap-2"><select aria-label={en ? 'Check type' : 'Вид проверки'} value={kind} onChange={e => setKind(e.target.value)} className="rounded-lg border p-2 text-sm"><option value="">{en ? 'All checks' : 'Все проверки'}</option>{checks.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <select aria-label={en ? 'Run status' : 'Статус запуска'} value={status} onChange={e => setStatus(e.target.value)} className="rounded-lg border p-2 text-sm"><option value="">{en ? 'All statuses' : 'Все статусы'}</option>{Object.keys(labels).map(key => <option key={key} value={key}>{labels[key as CheckStatus][en ? 1 : 0]}</option>)}</select></div>
      {recent.length === 0 ? <p className="mt-4 text-sm text-slate-500">{en ? 'No runs match these filters.' : 'Запусков по выбранным фильтрам нет.'}</p> :
        <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{[en ? 'Date' : 'Дата', en ? 'Check' : 'Проверка', en ? 'Status' : 'Статус', en ? 'Duration' : 'Время', en ? 'Result' : 'Результат', en ? 'Version' : 'Версия'].map(head => <th key={head} className="p-2">{head}</th>)}</tr></thead><tbody>{recent.map(run => <tr key={run.id} className="border-t"><td className="p-2">{date(run.created_at)}</td><td className="p-2">{run.check_id}</td><td className="p-2"><Badge status={run.status} en={en} run={run} /></td><td className="p-2">{run.duration_seconds?.toFixed(2) ?? '—'} s</td><td className="p-2"><button className="text-indigo-700 underline" onClick={() => void open(run.id)}>{savedRunLabel(run, en)}</button></td><td className="p-2 font-mono text-xs">{run.project_version?.slice(0, 8) || '—'}</td></tr>)}</tbody></table></div>}
    </section>

    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><h3 className="text-lg font-bold">{en ? 'Compare saved runs' : 'Сравнение запусков'}</h3>
      <div className="mt-3 flex flex-wrap gap-2">{[first, second].map((value, index) => <select key={index} aria-label={index ? en ? 'Second run' : 'Второй запуск' : en ? 'First run' : 'Первый запуск'} value={value} onChange={e => { if (index) setSecond(e.target.value); else setFirst(e.target.value); }} className="max-w-full rounded-lg border p-2 text-sm"><option value="">{index ? en ? 'Second run' : 'Второй запуск' : en ? 'First run' : 'Первый запуск'}</option>{history.map(run => <option key={run.id} value={run.id}>{date(run.created_at)} · {run.check_id} · {run.status} · {run.id.slice(0, 8)}</option>)}</select>)}<button disabled={!first || !second || first === second} onClick={() => void compare()} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-40">{en ? 'Compare' : 'Сравнить'}</button></div>
      {comparison && <div className="mt-4 text-sm">{!comparison.comparable ? <p>{comparison.reason}</p> : <><p>{en ? 'Duration change' : 'Изменение времени'}: {comparison.duration_delta_seconds?.toFixed(2)} s</p><p>{en ? 'Test count changes' : 'Изменение числа тестов'}: {JSON.stringify(comparison.count_delta)}</p>{([['became_passed', en ? 'Now passing' : 'Стали успешными'], ['became_failed', en ? 'Now failing' : 'Начали падать'], ['appeared', en ? 'Appeared' : 'Появились'], ['disappeared', en ? 'Disappeared' : 'Исчезли']] as const).map(([key, label]) => <p key={key} className="mt-2"><strong>{label}:</strong> {comparison[key]?.join(', ') || '—'}</p>)}<p className="mt-3 text-xs text-slate-500">{en ? 'Changes in test counts alone do not establish quality improvement.' : 'Само изменение количества тестов не доказывает улучшение качества.'}</p></>}</div>}
    </section>
  </div>;
}

function Metric({ title, value }: { title: string; value: ReactNode }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4"><p className="text-xs text-slate-500">{title}</p><div className="mt-2 text-2xl font-bold">{value}</div></div>;
}

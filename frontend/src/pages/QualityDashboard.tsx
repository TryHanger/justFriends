import { useCallback, useEffect, useMemo, useState } from 'react';
import { getCheckRun, getProductMeasurements, listCheckRuns, startCheckRun } from '../api';
import type { CheckRun, ProductMeasurement, ProductMeasurementsReport } from '../api';
import { getApiErrorMessage } from '../apiErrors';
import { testPurpose } from './qualityPresentation';

const characteristics = [
  ['Functional suitability', 'Функциональная пригодность'],
  ['Reliability', 'Надёжность'],
  ['Performance efficiency', 'Производительность'],
  ['Compatibility', 'Совместимость'],
  ['Interaction capability', 'Способность к взаимодействию'],
  ['Security', 'Информационная безопасность'],
  ['Maintainability', 'Сопровождаемость'],
  ['Flexibility', 'Гибкость'],
  ['Safety', 'Безопасность эксплуатации'],
] as const;

const complete = new Set(['passed', 'failed', 'skipped', 'error', 'timeout', 'unavailable', 'interrupted']);
function runLabel(run: CheckRun | null): string {
  if (!run) return 'Проверка ещё не запускалась';
  const { passed = 0, failed = 0, skipped = 0 } = run.counts;
  if (run.status === 'skipped' && passed > 0 && failed === 0 &&
      passed + skipped === run.cases.length) return `Тесты пройдены, ${skipped} пропущено`;
  if (run.status === 'passed') return 'Тесты пройдены';
  if (run.status === 'failed') return 'Есть ошибки тестов';
  if (run.status === 'queued') return 'Проверка в очереди';
  if (run.status === 'running') return 'Проверка выполняется';
  return 'Проверка не завершена';
}

function trend(item: ProductMeasurement): string {
  if (item.value === null || item.previous_value == null) return 'Для динамики нужны два измеренных запуска';
  const difference = +(item.value - item.previous_value).toFixed(2);
  const deltaUnit = item.unit === '%' ? 'п.п.' : item.unit;
  if (difference === 0) return `Без изменения относительно прошлого запуска (${item.previous_value} ${item.unit})`;
  const direction = difference > 0 ? '+' : '−';
  return `${direction}${Math.abs(difference).toLocaleString('ru-RU')} ${deltaUnit} к прошлому запуску (${item.previous_value} ${item.unit})`;
}

export default function QualityDashboard({ onOpenRun }: { onOpenRun: (id: string) => void }) {
  const [measurements, setMeasurements] = useState<ProductMeasurementsReport | null>(null);
  const [history, setHistory] = useState<CheckRun[]>([]);
  const [active, setActive] = useState<CheckRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      const [measured, runs] = await Promise.all([getProductMeasurements(), listCheckRuns('backend-tests')]);
      setMeasurements(measured);
      setHistory(runs);
      setError('');
    } catch (cause) { setError(getApiErrorMessage(cause, 'Не удалось загрузить оценку качества.')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => { void refresh(); }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);
  useEffect(() => {
    if (!active || complete.has(active.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await getCheckRun(active.id);
        setActive(next);
        if (complete.has(next.status)) void refresh();
      } catch (cause) { setError(getApiErrorMessage(cause, 'Не удалось обновить результат проверки.')); }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active, refresh]);

  const backend = active && complete.has(active.status) ? active : history.find(run => run.check_id === 'backend-tests') ?? active;
  const completed = backend && complete.has(backend.status) ? backend : null;
  const byId = useMemo(() => new Map(measurements?.measurements.map(item => [item.id, item]) ?? []), [measurements]);
  const evidence = new Set<string>();
  if (byId.get('backend-pass-share')?.state === 'measured' || byId.get('frontend-pass-share')?.state === 'measured') evidence.add('Functional suitability');
  if (completed?.cases.some(test => test.name.endsWith('::test_api_persist_retrieve_and_errors') && test.status === 'passed')) evidence.add('Reliability');
  if (byId.get('ruff-findings')?.state === 'measured' || byId.get('typescript-errors')?.state === 'measured') evidence.add('Maintainability');
  const skippedCases = completed?.cases.filter(test => test.status === 'skipped') ?? [];
  const passed = completed?.counts.passed ?? null;
  const failed = completed?.counts.failed ?? null;
  const executed = completed ? (completed.counts.passed ?? 0) + (completed.counts.failed ?? 0) : null;

  async function start() {
    setError('');
    try { setActive(await startCheckRun('backend-tests')); }
    catch (cause) { setError(getApiErrorMessage(cause, 'Не удалось запустить проверку.')); }
  }

  return <div className="space-y-5">
    <ol className="grid gap-2 text-xs font-semibold text-indigo-800 sm:grid-cols-4" aria-label="Этапы оценки качества">
      {['1. Запуск проверки', '2. Результат', '3. Оценка качества', '4. Динамика'].map(step => <li key={step} className="rounded-lg bg-indigo-50 px-3 py-2">{step}</li>)}
    </ol>
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><h2 className="text-xl font-bold">Качество программного продукта</h2>
          <p className="mt-1 text-sm text-slate-600">ISO/IEC 25010:2023 · свидетельства по отдельным характеристикам, без заявления о соответствии стандарту.</p></div>
        <span className="rounded-full bg-amber-100 px-3 py-1 text-sm font-semibold text-amber-900">{evidence.size ? 'Частично оценено' : 'Не оценено'}</span>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <Summary title="Успешных тестов" value={passed === null ? '—' : `${passed}/${executed}`} note={`${completed?.counts.skipped ?? 0} пропущено`} />
        <Summary title="Ошибок" value={failed ?? '—'} note="В последнем запуске pytest" />
        <Summary title="Характеристики" value={`${evidence.size}/9`} note="Есть частичные свидетельства" />
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button onClick={() => void start()} disabled={!!active && !complete.has(active.status)} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{active && !complete.has(active.status) ? 'Проверка выполняется…' : 'Запустить проверку'}</button>
        <span role="status" className="text-sm font-semibold text-slate-700">{runLabel(active && !complete.has(active.status) ? active : backend ?? null)}</span>
        {completed && <button onClick={() => onOpenRun(completed.id)} className="text-sm font-semibold text-indigo-700 underline">Открыть результат</button>}
      </div>
      {skippedCases.length > 0 && <details className="mt-3 text-sm"><summary className="cursor-pointer text-amber-900">Причины пропуска: {skippedCases.length}</summary><ul className="mt-2 list-disc pl-5">{skippedCases.map(test => <li key={test.name}><span className="font-mono text-xs">{test.name}</span>: {test.message || 'Причина не указана инструментом'}</li>)}</ul></details>}
      {error && <p role="alert" className="mt-3 rounded-lg bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
    </section>

    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="font-bold">Результат последней проверки</h3>
      {!completed ? <p className="mt-3 text-sm text-slate-500">{loading ? 'Загрузка результатов…' : 'Запустите проверку, чтобы увидеть отдельные тесты.'}</p> :
        <div className="mt-3 max-h-96 overflow-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b"><th className="p-2">Тест и назначение</th><th className="p-2">Статус</th><th className="p-2">Время</th></tr></thead><tbody>{completed.cases.map(test => <tr key={test.name} className="border-b align-top"><td className="p-2"><strong className="block font-medium">{testPurpose(test.name)}</strong><details><summary className="cursor-pointer text-xs text-indigo-700">Подробности теста</summary><p className="mt-1 break-all font-mono text-xs">{test.name}</p><p className="mt-1 text-xs">{test.message || 'Дополнительного сообщения нет.'}</p></details></td><td className="p-2">{test.status === 'passed' ? 'Успешно' : test.status === 'skipped' ? 'Пропущен' : 'Ошибка'}</td><td className="p-2">{test.duration_seconds.toFixed(2)} с</td></tr>)}</tbody></table></div>}
    </section>

    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="font-bold">Состояние оценки качества</h3>
      <p className="mt-1 text-xs text-slate-500">Свидетельство по тесту или инструменту не подтверждает характеристику целиком. Исходные названия ISO показаны в подсказках.</p>
      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{characteristics.map(([original, translated]) => <div key={original} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 p-3" title={original}><span className="text-sm font-medium">{translated}</span><span className={`shrink-0 rounded-full px-2 py-1 text-xs ${evidence.has(original) ? 'bg-amber-100 text-amber-900' : 'bg-slate-100 text-slate-600'}`}>{evidence.has(original) ? 'Частично проверено' : 'Не оценено'}</span></div>)}</div>
    </section>

    <section className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-bold">ISO/IEC 25023:2016 · измерения и динамика</h3><p className="mt-1 text-sm text-slate-600">Проектные показатели по сохранённым запускам. Это не процент качества ПО.</p></div><button onClick={() => void refresh()} className="rounded-lg border border-indigo-300 px-3 py-2 text-sm text-indigo-800">Обновить измерения</button></div>
      {measurements && <><div className="mt-4 grid gap-3 md:grid-cols-2">{measurements.measurements.map(item => <article key={item.id} className="rounded-lg border border-slate-200 bg-white p-4"><h4 className="font-semibold">{item.title}</h4><p className="mt-2 text-2xl font-bold">{item.value === null ? 'Нет данных' : `${item.value.toLocaleString('ru-RU')} ${item.unit}`}</p>{item.denominator !== null && <p className="text-xs font-medium text-slate-700">{item.value}% успешно среди выполненных тестов · {item.skipped} пропущено</p>}<p className="mt-2 text-sm text-indigo-800">{trend(item)}</p><p className="mt-2 text-xs text-slate-600">Метод: {item.method}</p><p className="mt-1 text-xs text-slate-600">Граница вывода: {item.limitation}</p><div className="mt-2 flex flex-wrap gap-3 text-sm">{item.source_run_id && <button onClick={() => onOpenRun(item.source_run_id!)} className="text-indigo-700 underline">Текущий результат</button>}{item.previous_run_id && <button onClick={() => onOpenRun(item.previous_run_id!)} className="text-indigo-700 underline">Предыдущий результат</button>}</div></article>)}</div><ul className="mt-3 list-disc pl-5 text-xs text-slate-600">{measurements.limitations.map(note => <li key={note}>{note}</li>)}</ul></>}
    </section>
  </div>;
}

function Summary({ title, value, note }: { title: string; value: string | number; note: string }) {
  return <div className="rounded-lg bg-slate-50 p-4"><p className="text-xs text-slate-500">{title}</p><p className="mt-1 text-3xl font-bold">{value}</p><p className="text-xs text-slate-600">{note}</p></div>;
}

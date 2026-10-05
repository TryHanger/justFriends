import { useEffect, useMemo, useState } from 'react';
import { getLifecycleState, getStandardsReference, runQualityChecks } from '../api';
import type { LifecycleState, QualityReport, StandardInfo } from '../api';

type Tab = 'catalog' | 'lifecycle' | 'quality';
const badge = (tone: 'good' | 'warn' | 'bad' | 'neutral') => ({
  good: 'bg-emerald-100 text-emerald-800', warn: 'bg-amber-100 text-amber-800',
  bad: 'bg-rose-100 text-rose-800', neutral: 'bg-slate-100 text-slate-700',
})[tone];

export default function Standards() {
  const [tab, setTab] = useState<Tab>('catalog');
  const [standards, setStandards] = useState<StandardInfo[]>([]);
  const [lifecycle, setLifecycle] = useState<LifecycleState | null>(null);
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState('');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([getStandardsReference(), getLifecycleState()])
      .then(([reference, state]) => { setStandards(reference); setLifecycle(state); })
      .catch(() => setError('Не удалось получить данные проекта. Проверьте запуск API.'))
      .finally(() => setLoading(false));
  }, []);

  const domains = useMemo(() => [...new Set(standards.map(s => s.domain))].sort(), [standards]);
  const visible = useMemo(() => standards.filter(s => {
    const needle = query.trim().toLocaleLowerCase();
    return (!domain || s.domain === domain) && (!needle ||
      [s.designation, s.domain, s.purpose].some(value => value.toLocaleLowerCase().includes(needle)));
  }), [standards, query, domain]);
  const organizations = useMemo(() => Object.entries(standards.reduce<Record<string, number>>((acc, item) => {
    acc[item.organization] = (acc[item.organization] || 0) + 1; return acc;
  }, {})).sort((a, b) => b[1] - a[1]), [standards]);
  const distribution = useMemo(() => Object.entries(standards.reduce<Record<string, number>>((acc, item) => {
    acc[item.domain] = (acc[item.domain] || 0) + 1; return acc;
  }, {})).sort((a, b) => b[1] - a[1]), [standards]);

  async function runChecks() {
    setRunning(true); setError('');
    try { setQuality(await runQualityChecks()); }
    catch { setError('Проверка недоступна. Запуск тестов разрешён только в локальном режиме API.'); }
    finally { setRunning(false); }
  }

  const tabLabels: Record<Tab, string> = { catalog: 'Каталог', lifecycle: 'Жизненный цикл', quality: 'Качество и тесты' };
  return <div className="space-y-6 text-slate-900">
    <section className="rounded-2xl bg-slate-900 px-6 py-7 text-white shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-300">Инженерная панель · учебная адаптация лабораторных №1–6</p>
      <h1 className="mt-2 text-3xl font-bold">Стандарты и проверка проекта</h1>
      <p className="mt-2 max-w-3xl text-sm text-slate-300">Каталог стандартов, свидетельства в репозитории, карта процессов и реальные результаты тестов. Наличие артефакта означает только наличие файла, а не выполнение всех требований стандарта.</p>
      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl bg-white/10 p-4"><div className="text-3xl font-bold">{standards.length}</div><div className="text-xs text-slate-300">стандартов в выборке</div></div>
        <div className="rounded-xl bg-white/10 p-4"><div className="text-3xl font-bold">{lifecycle?.processes.length ?? '—'}</div><div className="text-xs text-slate-300">процессов в модели</div></div>
        <div className="rounded-xl bg-white/10 p-4"><div className="text-3xl font-bold">{quality ? `${quality.passed_tests}/${quality.total_tests}` : '—'}</div><div className="text-xs text-slate-300">тестов пройдено в последнем запуске</div></div>
      </div>
    </section>

    {error && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</div>}
    <div role="tablist" aria-label="Разделы стандартов" className="flex flex-wrap gap-2 border-b border-slate-200 pb-3">
      {(Object.keys(tabLabels) as Tab[]).map(key => <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)} className={`rounded-lg px-4 py-2 text-sm font-semibold ${tab === key ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'}`}>{tabLabels[key]}</button>)}
    </div>

    {loading && <p className="p-8 text-center text-slate-500">Загрузка…</p>}
    {!loading && tab === 'catalog' && <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-2">
        <Distribution title="По организациям" values={organizations} total={standards.length} />
        <Distribution title="По областям" values={distribution} total={standards.length} />
      </div>
      <p className="text-xs text-slate-500">Распределение отражает выбранные {standards.length} стандартов, а не распространённость стандартов в мире.</p>
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="flex-1 text-sm font-medium">Поиск по обозначению, области и назначению<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Например, 25010 или безопасность" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-indigo-500" /></label>
          <label className="text-sm font-medium">Область<select value={domain} onChange={e => setDomain(e.target.value)} className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 sm:w-56"><option value="">Все области</option>{domains.map(d => <option key={d}>{d}</option>)}</select></label>
        </div>
        <p className="mt-3 text-xs text-slate-500">Найдено: {visible.length}</p>
      </div>
      {visible.length === 0 ? <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center text-slate-500">Стандарты по запросу не найдены.</div> :
        <div className="grid gap-4 lg:grid-cols-2">{visible.map(s => <article key={s.designation} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-2"><h2 className="text-lg font-bold text-indigo-700">{s.designation}</h2><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${badge('neutral')}`}>{s.organization}</span></div>
          <p className="mt-1 text-sm font-medium">{s.title}</p><p className="mt-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{s.domain}</p>
          <p className="mt-3 text-sm text-slate-700">{s.purpose}</p>
          <p className="mt-3 text-sm"><strong>Применение:</strong> {s.example_use}</p>
          <p className="mt-3 text-xs text-slate-600"><strong>Артефакты проекта:</strong> {s.project_evidence.length ? s.project_evidence.join(', ') : 'пока не указаны'}</p>
          <a href={s.source_url} target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm font-semibold text-indigo-600 hover:underline">Описание стандарта ↗</a>
        </article>)}</div>}
    </div>}

    {!loading && tab === 'lifecycle' && lifecycle && <div className="space-y-5">
      <div className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold">Готовность: {lifecycle.readiness === 'ready' ? 'готово' : lifecycle.readiness === 'conditional' ? 'условно' : 'не готово'}</h2><p className="mt-1 text-sm text-slate-600">Решение основано на наличии артефактов и обязательной пользовательской валидации. Оно не подтверждает эксплуатационную готовность без испытаний.</p></div>
      <div className="grid gap-4 md:grid-cols-2">{lifecycle.processes.map(p => <article key={p.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex justify-between gap-2"><h3 className="font-bold">{p.name}</h3><span className={`h-fit rounded-full px-2 py-1 text-xs font-semibold ${badge(p.status === 'evidenced' ? 'good' : p.status === 'partial' ? 'warn' : 'bad')}`}>{p.status === 'evidenced' ? 'есть свидетельства' : p.status === 'partial' ? 'частично' : 'нет свидетельств'}</span></div>
        <p className="mt-1 text-xs text-slate-500">Ответственный: {p.responsible} · Зависит от: {p.dependencies.length ? p.dependencies.join(', ') : 'начала проекта'}</p>
        <p className="mt-3 text-sm"><strong>Вход:</strong> {p.inputs.length ? p.inputs.join(', ') : 'запрос заинтересованных сторон'}</p>
        <p className="mt-2 text-sm"><strong>Результат:</strong> {p.outputs.join(', ')}</p>
        <p className="mt-2 text-sm"><strong>Файлы:</strong> {p.evidence.length ? p.evidence.join(', ') : 'не найдены'}</p>
        {p.gaps.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm text-rose-700">{p.gaps.map(gap => <li key={gap}>{gap}</li>)}</ul>}
      </article>)}</div>
    </div>}

    {!loading && tab === 'quality' && <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-5"><div><h2 className="text-lg font-bold">ISO/IEC 25010:2023 · профиль качества</h2><p className="text-sm text-slate-600">Девять характеристик; измеренные проверки отделены от непроверенных.</p></div><button onClick={runChecks} disabled={running} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">{running ? 'Тесты выполняются…' : 'Запустить тесты'}</button></div>
      {quality ? <>
        <div className={`rounded-xl p-5 ${quality.overall_status === 'PASS' ? 'bg-emerald-50' : quality.overall_status === 'FAIL' ? 'bg-rose-50' : 'bg-amber-50'}`}><div className="text-xl font-bold">{quality.overall_status}</div><p className="text-sm">Пройдено {quality.passed_tests} из {quality.total_tests}; ошибок {quality.failed_tests}; пропущено {quality.skipped_tests}. Время {quality.duration_seconds.toFixed(2)} с.</p></div>
        <div className="grid gap-3 md:grid-cols-2">{quality.metrics.map(m => <article key={m.characteristic} className="rounded-xl border border-slate-200 bg-white p-4"><div className="flex justify-between gap-2"><h3 className="font-bold">{m.characteristic}</h3><span className={`rounded-full px-2 py-1 text-xs font-semibold ${badge(m.status === 'passed' ? 'good' : m.status === 'failed' ? 'bad' : 'neutral')}`}>{m.status === 'passed' ? 'пройдено' : m.status === 'failed' ? 'ошибка' : 'не оценено'}</span></div><p className="mt-2 text-sm">{m.criterion}</p><p className="mt-1 text-xs text-slate-500">Метод: {m.method}</p><p className="mt-2 text-sm text-slate-700">{m.observed}</p></article>)}</div>
        <div className="rounded-xl border border-slate-200 bg-white p-5"><h3 className="font-bold">Результаты отдельных тестов</h3><div className="mt-3 max-h-96 overflow-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b"><th className="py-2">Тест</th><th className="py-2">Статус</th><th className="py-2">Сообщение</th></tr></thead><tbody>{quality.cases.map(c => <tr key={c.name} className="border-b align-top"><td className="py-2 pr-3 font-mono text-xs">{c.name}</td><td className="py-2 pr-3">{c.status}</td><td className="py-2 text-rose-700">{c.message}</td></tr>)}</tbody></table></div></div>
        {quality.limitations.map(note => <p key={note} className="text-xs text-slate-500">{note}</p>)}
      </> : <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">Запустите тесты, чтобы увидеть проверенный отчёт. До запуска оценки нет.</p>}
    </div>}
  </div>;
}

function Distribution({ title, values, total }: { title: string; values: [string, number][]; total: number }) {
  return <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><h2 className="font-bold">{title}</h2><div className="mt-4 space-y-3">{values.map(([label, count]) => <div key={label}><div className="mb-1 flex justify-between gap-2 text-xs"><span>{label}</span><strong>{count}</strong></div><div className="h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-indigo-500" style={{ width: `${total ? count / total * 100 : 0}%` }} /></div></div>)}</div></section>;
}

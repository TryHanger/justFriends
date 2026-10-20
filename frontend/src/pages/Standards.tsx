import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getLifecycleState, getStandardsReference } from '../api';
import type { LifecycleState, StandardInfo } from '../api';
import { getApiErrorMessage } from '../apiErrors';
import QualityCenter from './QualityCenter';
import QualityDashboard from './QualityDashboard';

type Tab = 'catalog' | 'lifecycle' | 'quality' | 'checks';
const badge = (tone: 'good' | 'warn' | 'bad' | 'neutral') => ({
  good: 'bg-emerald-100 text-emerald-800', warn: 'bg-amber-100 text-amber-800',
  bad: 'bg-rose-100 text-rose-800', neutral: 'bg-slate-100 text-slate-700',
})[tone];

export default function Standards() {
  const [tab, setTab] = useState<Tab>('catalog');
  const [standards, setStandards] = useState<StandardInfo[]>([]);
  const [lifecycle, setLifecycle] = useState<LifecycleState | null>(null);
  const [sourceRunId, setSourceRunId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const requestVersion = useRef(0);

  const loadData = useCallback(() => {
    const version = ++requestVersion.current;
    Promise.all([getStandardsReference(), getLifecycleState()])
      .then(([reference, state]) => { if (version === requestVersion.current) { setStandards(reference); setLifecycle(state); } })
      .catch(e => { if (version === requestVersion.current) setError(getApiErrorMessage(e, 'Не удалось получить данные проекта. Проверьте запуск API.')); })
      .finally(() => { if (version === requestVersion.current) setLoading(false); });
  }, []);
  useEffect(() => { loadData(); }, [loadData]);

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

  const tabLabels: Record<Tab, string> = { catalog: 'Каталог', lifecycle: 'Жизненный цикл', quality: 'Качество и тесты', checks: 'Проверки проекта' };
  return <div className="space-y-6 text-slate-900">
    <section className="rounded-2xl bg-slate-900 px-6 py-7 text-white shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-300">Инженерная панель · учебная адаптация лабораторных №1–6</p>
      <h1 className="mt-2 text-3xl font-bold">Стандарты и проверка проекта</h1>
      <p className="mt-2 max-w-3xl text-sm text-slate-300">Каталог стандартов, свидетельства в репозитории, карта процессов и реальные результаты тестов. Наличие артефакта означает только наличие файла, а не выполнение всех требований стандарта.</p>
      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl bg-white/10 p-4"><div className="text-3xl font-bold">{standards.length}</div><div className="text-xs text-slate-300">стандартов в выборке</div></div>
        <div className="rounded-xl bg-white/10 p-4"><div className="text-3xl font-bold">{lifecycle?.processes.length ?? '—'}</div><div className="text-xs text-slate-300">процессов в модели</div></div>
        <div className="rounded-xl bg-white/10 p-4"><div className="text-3xl font-bold">5</div><div className="text-xs text-slate-300">видов проверок проекта</div></div>
      </div>
    </section>

    {error && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error} <button onClick={() => { setLoading(true); setError(''); loadData(); }} className="ml-2 font-semibold underline">Повторить загрузку</button></div>}
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
      <div className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold">Готовность: {lifecycle.readiness === 'ready' ? 'готово' : lifecycle.readiness === 'conditional' ? 'условно' : 'не готово'}</h2><p className="mt-1 text-sm text-slate-600">Решение основано на наличии артефактов и обязательной пользовательской валидации. Оно не подтверждает эксплуатационную готовность без испытаний.</p>{lifecycle.last_checked_at && <p className="mt-2 text-xs text-slate-500">Последняя проверка: {new Date(lifecycle.last_checked_at).toLocaleString('ru-RU')}</p>}</div>
      <div className="grid gap-4 md:grid-cols-2">{lifecycle.processes.map(p => <article key={p.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex justify-between gap-2"><h3 className="font-bold">{p.name}</h3><span className={`h-fit rounded-full px-2 py-1 text-xs font-semibold ${badge(p.status === 'evidenced' ? 'good' : p.status === 'partial' ? 'warn' : 'bad')}`}>{p.status === 'evidenced' ? 'есть свидетельства' : p.status === 'partial' ? 'частично' : 'нет свидетельств'}</span></div>
        <p className="mt-1 text-xs text-slate-500">Ответственный: {p.responsible} · Зависит от: {p.dependencies.length ? p.dependencies.join(', ') : 'начала проекта'}</p>
        <p className="mt-3 text-sm"><strong>Вход:</strong> {p.inputs.length ? p.inputs.join(', ') : 'запрос заинтересованных сторон'}</p>
        <p className="mt-2 text-sm"><strong>Результат:</strong> {p.outputs.join(', ')}</p>
        <p className="mt-2 text-sm"><strong>Файлы:</strong> {p.evidence.length ? p.evidence.join(', ') : 'не найдены'}</p>
        {p.gaps.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm text-rose-700">{p.gaps.map(gap => <li key={gap}>{gap}</li>)}</ul>}
      </article>)}</div>
    </div>}

    {!loading && tab === 'quality' && <QualityDashboard onOpenRun={id => { setSourceRunId(id); setTab('checks'); }} />}
    {tab === 'checks' && <QualityCenter initialRunId={sourceRunId} />}
  </div>;
}

function Distribution({ title, values, total }: { title: string; values: [string, number][]; total: number }) {
  return <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><h2 className="font-bold">{title}</h2><div className="mt-4 space-y-3">{values.map(([label, count]) => <div key={label}><div className="mb-1 flex justify-between gap-2 text-xs"><span>{label}</span><strong>{count}</strong></div><div className="h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-indigo-500" style={{ width: `${total ? count / total * 100 : 0}%` }} /></div></div>)}</div></section>;
}

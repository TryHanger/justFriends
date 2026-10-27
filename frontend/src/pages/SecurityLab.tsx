import { useRef, useState } from 'react';
import { ArrowRight, Download, Play, ShieldCheck } from 'lucide-react';
import { reviewSecurity } from '../api';
import type { SecurityReview } from '../api';
import { getApiErrorMessage } from '../apiErrors';

const examples = [
  {
    title: 'SQL-запрос', requirement: 'Ввод пользователя передаётся в БД отдельно от текста запроса.',
    before: `def find_user(db, name):\n    return db.execute(\n        "SELECT * FROM users WHERE name = '" + name + "'"\n    ).fetchall()`,
    after: `def find_user(db, name):\n    return db.execute(\n        "SELECT * FROM users WHERE name = ?", (name,)\n    ).fetchall()`,
    proof: 'В локальной тестовой БД передайте имя с кавычкой и строку SQL-инъекции. Проверьте, что возвращается только точное совпадение и данные не меняются.',
  },
  {
    title: 'Обработка данных', requirement: 'Строка с данными не должна становиться исполняемым кодом.',
    before: `def read_options(user_text):\n    return eval(user_text)`,
    after: `import json\n\ndef read_options(user_text):\n    return json.loads(user_text)`,
    proof: 'Проверьте корректный JSON и некорректную строку. Ожидайте данные в первом случае и обработанную ошибку во втором; Python-выражение не должно выполняться.',
  },
  {
    title: 'Системная команда', requirement: 'Команда запускается без оболочки, аргументы ограничены допустимыми значениями.',
    before: `import subprocess\n\ndef list_files(user_path):\n    return subprocess.run("ls " + user_path, shell=True)`,
    after: `import subprocess\n\ndef list_files(user_path):\n    if user_path not in {"data", "models"}:\n        raise ValueError("Недопустимый каталог")\n    return subprocess.run(\n        ["ls", "--", user_path], shell=False, check=True\n    )`,
    proof: 'В тесте подмените subprocess.run. Проверьте список аргументов и shell=False; ввод вне списка должен отклоняться до вызова команды. Пример ls предназначен для Linux-контейнера.',
  },
];

function csvCell(value: string | number) {
  const text = String(value);
  return `"${(/^[=+@\-\t\r]/.test(text) ? "'" + text : text).replaceAll('"', '""')}"`;
}

export default function SecurityLab() {
  const [example, setExample] = useState(0);
  const [before, setBefore] = useState(examples[0].before);
  const [after, setAfter] = useState(examples[0].after);
  const [likelihood, setLikelihood] = useState(3);
  const [impact, setImpact] = useState(3);
  const [result, setResult] = useState<SecurityReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const version = useRef(0);
  const selected = examples[example];

  function invalidate() { version.current++; setResult(null); setError(''); setBusy(false); }
  function select(index: number) {
    invalidate(); setExample(index); setBefore(examples[index].before); setAfter(examples[index].after);
  }
  async function analyze() {
    const current = ++version.current;
    setBusy(true); setError(''); setResult(null);
    try {
      const next = await reviewSecurity(before, after, likelihood, impact);
      if (version.current === current) setResult(next);
    } catch (cause) {
      if (version.current === current) setError(getApiErrorMessage(cause, 'Не удалось выполнить анализ. Проверьте подключение к API.'));
    } finally { if (version.current === current) setBusy(false); }
  }
  function download() {
    if (!result) return;
    const rows: (string | number)[][] = [['Версия', 'Файл', 'Строка', 'Правило', 'Проблема', 'OWASP', 'Последствия', 'Рекомендация', 'P', 'I', 'R', 'Статус разбора']];
    for (const [label, review] of [['До', result.before], ['После', result.after]] as const) {
      if (!review.findings.length) rows.push([label, 'example.py', '', '', review.syntax_error ?? 'Предупреждения трёх правил не найдены', '', '', '', likelihood, impact, result.risk_score, review.syntax_error ? 'Ошибка' : 'Разобран']);
      review.findings.forEach(f => rows.push([label, 'example.py', f.line, f.rule, f.title, f.category, f.consequence, f.recommendation, likelihood, impact, result.risk_score, 'Разобран']));
    }
    rows.push(['Примечание', 'Учебный AST-анализ; совпадение по типу правила и количеству, без идентификации отдельных дефектов. R = P × I — выбранный приоритет проверки, не измеренный остаточный риск.']);
    const url = URL.createObjectURL(new Blob(['\uFEFF' + rows.map(row => row.map(csvCell).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'security-review.csv'; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const parsed = result && !result.before.syntax_error && !result.after.syntax_error;

  return <div className="space-y-4">
    <section className="overflow-hidden rounded-2xl border border-indigo-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4 bg-indigo-50 px-5 py-5">
        <div className="max-w-2xl"><div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-700"><ShieldCheck className="h-4 w-4" />Практическая работа №15–16</div>
          <h2 className="mt-2 text-2xl font-bold">От требования к проверенному исправлению</h2>
          <p className="mt-2 text-sm text-slate-600">Ноу-хау проекта: требование безопасности, сравнение кода и доказательство проверки собраны в одном рабочем окне.</p></div>
        <div className="flex flex-wrap gap-2 text-xs font-semibold"><a className="rounded-full border border-indigo-200 bg-white px-3 py-1.5 text-indigo-700 hover:underline" href="https://www.iso.org/standard/44378.html" target="_blank" rel="noreferrer">ISO/IEC 27034-1 ↗</a><a className="rounded-full border border-indigo-200 bg-white px-3 py-1.5 text-indigo-700 hover:underline" href="https://top10.owasp.org/2025/A05_2025-Injection/" target="_blank" rel="noreferrer">OWASP A05:2025 ↗</a></div>
      </div>
      <div className="px-5 py-4">
        <ol className="grid gap-2 text-sm sm:grid-cols-3" aria-label="Связь со стандартами">
          {[
            ['01', 'Требование', 'ISO/IEC 27034: встроить защиту в разработку.'],
            ['02', 'Контроль', 'OWASP: найти условия для инъекции.'],
            ['03', 'Свидетельство', 'Сравнить версии и выгрузить результат.'],
          ].map(([n, title, text]) => <li key={n} className="flex gap-3 rounded-xl bg-slate-50 p-3"><span className="text-lg font-bold text-indigo-300">{n}</span><div><p className="font-semibold">{title}</p><p className="mt-1 text-xs leading-5 text-slate-500">{text}</p></div></li>)}
        </ol>
        <p className="mt-3 text-xs text-slate-500">Учебная реализация по мотивам заданий 1, 3 и 4. AST-анализ трёх конструкций; сравнение не использует Bandit. Это демонстрация подхода, а не подтверждение соответствия стандарту.</p>
      </div>
    </section>

    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" aria-label="Анализ безопасности кода">
      <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-bold">1. Выберите пример и сравните версии</h3><div className="flex flex-wrap gap-1.5">{examples.map((item, index) => <button key={item.title} aria-pressed={example === index} onClick={() => select(index)} className={`rounded-lg px-3 py-2 text-xs font-semibold ${example === index ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>{item.title}</button>)}</div></div>
      <p className="my-3 text-sm text-slate-600"><strong className="text-slate-900">Требование: </strong>{selected.requirement}</p>
      <div className="grid gap-3 lg:grid-cols-2">{[
        { label: 'До исправления', value: before, set: setBefore },
        { label: 'После исправления', value: after, set: setAfter },
      ].map(field => <label key={field.label} className="block text-xs font-semibold text-slate-600">{field.label}<textarea spellCheck={false} maxLength={12000} value={field.value} onChange={event => { invalidate(); field.set(event.target.value); }} className="mt-2 h-52 w-full resize-y rounded-xl border border-slate-700 bg-slate-900 p-4 font-mono text-xs leading-6 text-slate-100 outline-none focus:ring-2 focus:ring-indigo-400" /></label>)}</div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="text-xs font-medium text-slate-600">Вероятность P<select value={likelihood} onChange={e => { invalidate(); setLikelihood(Number(e.target.value)); }} className="mt-1 block rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">{[1, 2, 3].map(n => <option key={n} value={n}>{n} · {['Низкая', 'Средняя', 'Высокая'][n - 1]}</option>)}</select></label>
        <label className="text-xs font-medium text-slate-600">Последствия I<select value={impact} onChange={e => { invalidate(); setImpact(Number(e.target.value)); }} className="mt-1 block rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">{[1, 2, 3].map(n => <option key={n} value={n}>{n} · {['Низкие', 'Средние', 'Высокие'][n - 1]}</option>)}</select></label>
        <button disabled={busy || !before.trim() || !after.trim()} onClick={() => void analyze()} className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"><Play className="h-4 w-4" />{busy ? 'Анализируем…' : 'Проверить обе версии'}</button>
        <span className="pb-2 text-xs text-slate-500">Код разбирается на сервере без выполнения и сохранения.</span>
      </div>
      <p className="mt-3 text-xs text-slate-500">Начальное допущение: недоверенный ввод доступен извне (P = 3), последствия затрагивают данные или выполнение кода (I = 3). Измените оценки под свой сценарий. R = P × I: 1–2 низкий, 3–4 средний, 6–9 высокий. Это учебная шкала из задания.</p>
      {error && <p role="alert" className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
      {result && <div className="mt-5 border-t border-slate-100 pt-4" aria-live="polite">
        <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-bold">2. Результат анализа</h3><button onClick={download} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700"><Download className="h-4 w-4" />Скачать CSV</button></div>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">{[
          ['До → после', parsed ? `${result.before.findings.length} → ${result.after.findings.length}` : 'Нет сравнения'],
          ['Исчезло предупреждений', parsed ? result.removed : '—'],
          ['Осталось / появилось', parsed ? `${result.remaining} / ${result.introduced}` : '—'],
          ['Приоритет проверки', `${result.risk_score}/9 · ${result.risk_level}`],
        ].map(([title, value]) => <div key={title} className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">{title}</p><p className="mt-1 text-lg font-bold">{value}</p></div>)}</div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">{([
          ['До исправления', result.before], ['После исправления', result.after],
        ] as const).map(([label, data]) => {
          return <div key={String(label)} className="rounded-xl border border-slate-200 p-3"><h4 className="text-xs font-bold text-slate-500">{String(label)}</h4>{data.syntax_error ? <p role="alert" className="mt-2 text-sm text-rose-700">{data.syntax_error}</p> : data.findings.length ? data.findings.map(f => <div key={`${f.rule}-${f.line}`} className="mt-3 border-l-2 border-amber-400 pl-3"><p className="text-sm font-semibold">{f.title}</p><p className="mt-1 text-xs text-amber-800">Строка {f.line} · {f.category}</p><p className="mt-2 text-xs leading-5 text-slate-600">{f.consequence}</p><p className="mt-1 text-xs leading-5"><strong>Исправление: </strong>{f.recommendation}</p></div>) : <p className="mt-2 text-sm text-emerald-700">Предупреждения трёх правил не найдены.</p>}</div>;
        })}</div>
        <p className="mt-3 text-xs leading-5 text-slate-500">Сравнение учитывает тип и количество предупреждений, а не номера строк. Перемещение или замена одного дефекта другим того же типа требуют ручной проверки. Анализатор не отслеживает поток данных, SQL через переменные, обёртки и переопределения имён. Исчезновение предупреждения не доказывает устранение уязвимости; остаточный риск не измерен.</p>
      </div>}
    </section>

    <section className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-5">
      <div className="flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-emerald-700" /><h3 className="font-bold">3. Что показать на защите · 2 минуты</h3></div>
      <ol className="mt-3 grid gap-3 text-sm md:grid-cols-3">{[
        ['Покажите требование', 'Выберите SQL-запрос. Объясните, почему ввод должен передаваться отдельно от команды.'],
        ['Покажите изменение', 'Нажмите «Проверить обе версии». Найдите A05:2025 и покажите замену склейки строк параметром ?.'],
        ['Покажите свидетельство', 'Скачайте CSV. Объясните, каким тестом подтвердите исправление и что ещё нужно проверить.'],
      ].map(([title, text]) => <li key={title}><p className="flex items-center gap-2 font-semibold text-emerald-900"><ArrowRight className="h-3 w-3 shrink-0" />{title}</p><p className="mt-1 text-xs leading-5 text-slate-600">{text}</p></li>)}</ol>
      <details className="mt-4 border-t border-emerald-200 pt-3"><summary className="cursor-pointer text-sm font-semibold text-emerald-900">Как подтвердить исправление текущего примера</summary><p className="mt-2 text-sm leading-6 text-slate-700">{selected.proof}</p><p className="mt-2 text-xs text-slate-500">Поведенческие тесты примера здесь не запускаются. В проекте связь со стандартом показана цепочкой «требование → контроль → результат → повторная проверка».</p></details>
    </section>
  </div>;
}

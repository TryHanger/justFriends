"""Side-by-side look at a local open model (KazLLM by default) against gpt-4o and Claude.

The metrics (scripts/eval_kk_usage_direct.py) say KazLLM is near chance on the direct
question; this shows what it actually answers. `run` passes Abai poems and dictionary
quotations through the same analysis as the site (one-pass LLM detection, no gpt-4o
second stage) and asks the direct question with a free-form JSON answer and a reason.
Answers are cached per item, so an interrupted run resumes. `html` writes a page next to
the cache; it quotes the copyrighted dictionary, so it stays out of git and public places.

    python -m scripts.compare_kazllm run --poems 12 --quotations 30
    python -m scripts.compare_kazllm html

With --lenient (separate cache files) values outside the closed lists are replaced instead
of rejecting the answer, the format note asks for values rather than the schema, the token
limit is 3072, and the raw model output is kept, so the content of every answer is visible.
"""

import argparse
import html
import json
import os
import random
import re
import time
from pathlib import Path

ROOT = Path("data/processed/kazllm_compare")
QUEUE = Path("data/processed/kk_ensemble/queue.jsonl")
USAGE = Path("data/processed/kk_usage")
LABEL_RU = {
    "metaphor": "метафора",
    "simile": "сравнение",
    "personification": "олицетворение",
    "metonymy": "метонимия",
    "idiom": "идиома",
}


LENIENT_NOTE = (
    " Проверка формата мягкая: значение не из списка (например, область «abstract») заменено"
    " на «другое», а не отклоняет весь ответ; под каждым ответом — что модель написала сама."
)


def short(model: str) -> str:
    return model.split("/")[-1]


def tag(args) -> str:
    """Cache and page name: the lenient run is kept apart from the strict one."""
    return short(args.model) + ("-lenient" if args.lenient else "")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def poems(count: int):
    from app.nlp.corpus import read_corpus

    return list(read_corpus(QUEUE))[:count]


def quotations(count: int) -> list[dict]:
    """A class-balanced subset of the 160-quotation sample, the same for every run."""
    from scripts.eval_kk_usage_direct import quotations as sample

    records = sample()
    chosen = []
    for usage in ("metaphorical", "literal"):
        group = sorted((r for r in records if r["usage_type"] == usage), key=lambda r: r["id"])
        chosen += random.Random(0).sample(group, min(count // 2, len(group)))
    return sorted(chosen, key=lambda r: r["id"])


def run(args) -> None:
    # Pure local model: the site's Kazakh second stage would otherwise ask gpt-4o.
    os.environ.update(
        HF_MODEL=args.model,
        HF_LOAD_4BIT="true",
        HF_LENIENT=str(args.lenient).lower(),
        NLP_TWO_STAGE_LANGUAGES="",
    )
    from app.nlp.__main__ import make_pipeline
    from app.nlp.usage import INSTRUCTIONS, RUSSIAN_REASON, SCHEMA, direct_question

    pipeline = make_pipeline("hf", None)
    detector = pipeline.detector
    if args.lenient:
        detector.max_new_tokens = 3072
    name = tag(args)
    jobs = [("poems", r.id, r.text, None) for r in poems(args.poems)]
    jobs += [("quotes", r["id"], r["text"], None) for r in quotations(args.quotations)]
    jobs += [("direct", r["id"], None, r) for r in quotations(args.quotations)]
    for number, (kind, item_id, text, record) in enumerate(jobs, 1):
        path = ROOT / f"{kind}-{name}.json"
        done = load_json(path)
        if item_id in done and "error" not in done[item_id]:
            continue
        started = time.time()
        detector.outputs = []
        try:
            if kind == "direct":
                question = direct_question(
                    record["text"], record["start"], record["end"], record["target"]
                )
                answer, _ = detector._complete(INSTRUCTIONS + RUSSIAN_REASON, question, SCHEMA, {})
                done[item_id] = json.loads(answer)
            else:
                done[item_id] = pipeline.analyze(text, "kk").model_dump()
        except Exception as exc:  # noqa: BLE001 - shown on the page, retried on the next run
            done[item_id] = {"error": f"{type(exc).__name__}: {exc}"[:700]}
        if args.lenient and detector.outputs:
            # The first call is the answer itself; a later one may be the Russian pass.
            done[item_id]["raw"] = detector.outputs[0]["text"]
            done[item_id]["repairs"] = sum(o["repairs"] for o in detector.outputs)
        save_json(path, done)
        status = "ошибка" if "error" in done[item_id] else "готово"
        print(
            f"{number}/{len(jobs)} {kind} {item_id}: {status}, {time.time() - started:.0f} с",
            flush=True,
        )


# ---------------------------------------------------------------- page


def highlight(text: str, spans) -> str:
    """Text with figure spans marked; overlapping spans are merged."""
    marks = sorted((s["start"], s["end"]) for s in spans if s.get("end", 0) > s.get("start", 0))
    merged = []
    for start, end in marks:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    out, position = [], 0
    for start, end in merged:
        out += [html.escape(text[position:start]), f"<mark>{html.escape(text[start:end])}</mark>"]
        position = end
    out.append(html.escape(text[position:]))
    return "".join(out).replace("\n", "<br>")


def error_ru(error: str) -> str:
    """What went wrong, in words, for a failed analysis."""
    if "literal_error" in error:
        return "ответ не принят: модель вписала область или тип не из списка"
    if "max_new_tokens" in error:
        return "ответ не принят: модель не уложилась в 2048 токенов"
    if "invalid or incomplete" in error or "no JSON" in error:
        return "ответ не принят: модель выдала испорченный JSON"
    if "Overlapping" in error:
        return "ответ не принят: модель отметила пересекающиеся фрагменты"
    return "ошибка"


def failure(error: str) -> str:
    return (
        f'<p class="error">{error_ru(error)}</p>'
        f'<details class="muted"><summary>подробно</summary>{html.escape(error)}</details>'
    )


def raw_output(result: dict) -> str:
    """The lenient run keeps what the model actually wrote and how many values were replaced."""
    note = ""
    if result.get("repairs"):
        note = f'<p class="muted">Заменено значений не из списка: {result["repairs"]}</p>'
    if result.get("raw"):
        note += (
            '<details class="muted"><summary>что ответила модель</summary>'
            f"<pre>{html.escape(result['raw'])}</pre></details>"
        )
    return note


def direct_answer(result: dict) -> tuple[str | None, str]:
    """Usage and reason; local models sometimes nest them in "properties" or echo the schema."""
    for answer in (result, result.get("properties", {})):
        if isinstance(answer.get("usage"), str):
            return answer["usage"], answer.get("reason", "")
    # Lenient run: an unescaped quote breaks the JSON, but the verdict itself is readable.
    found = re.search(
        r'"usage":\s*"(literal|metaphorical)",\s*"reason":\s*"(.*)"\s*}',
        result.get("raw", ""),
        re.S,
    )
    if found:
        return found[1], found[2] + " (из испорченного JSON)"
    if "error" in result:
        return None, error_ru(result["error"])
    return None, "вместо ответа вернула пустой шаблон JSON из инструкции"


def figures(text: str, result: dict | None) -> str:
    if result is None:
        return '<p class="muted">нет прогона</p>'
    if "error" in result:
        return failure(result["error"]) + raw_output(result)
    spans = result.get("metaphors", [])
    items = "".join(
        f"<li><b>{html.escape(s['text'])}</b> — {LABEL_RU.get(s['label'], s['label'])}"
        f'<br><span class="muted">{html.escape(s.get("rationale") or "")}</span></li>'
        for s in spans
    )
    return (
        f'<p class="poem">{highlight(text, spans)}</p>'
        f'<p class="count">Фигур: {len(spans)}</p><ul>{items}</ul>' + raw_output(result)
    )


def silver(path: Path) -> dict:
    """Claude's annotations are a corpus (jsonl with spans), the other runs are predictions."""
    if path.suffix == ".jsonl" and path.exists():
        out = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            # Its rationale is a fixed note; the tenor and ground say what the image means.
            spans = [
                {
                    **s,
                    "text": record["text"][s["start"] : s["end"]],
                    "rationale": "; ".join(
                        f"{key}: {s[field]}"
                        for key, field in (("тема", "tenor"), ("основание", "ground"))
                        if s.get(field)
                    ),
                }
                for s in record["spans"]
            ]
            out[record["id"]] = {"metaphors": spans}
        return out
    return load_json(path)


def headword_marked(record: dict, result: dict | None) -> str:
    if not result or "error" in result:
        return "—"
    hit = any(
        s["start"] < record["end"] and s["end"] > record["start"] for s in result["metaphors"]
    )
    return "переносное" if hit else "прямое"


def page(args) -> Path:
    name = short(args.model)
    kinds = ("poems", "quotes", "direct")
    own = {kind: load_json(ROOT / f"{kind}-{tag(args)}.json") for kind in kinds}
    strict = {kind: load_json(ROOT / f"{kind}-{name}.json") for kind in kinds}
    gpt_mini = load_json(Path("data/processed/kk_ensemble/gpt-4o-mini.json"))
    claude = silver(Path("data/processed/kk_ensemble/claude-opus-5-5.jsonl"))
    gpt_direct = load_json(USAGE / "direct-gpt-4o.json")
    gpt_two_stage = load_json(USAGE / "pred-two-stage-allwords-gpt-4o.json")
    usage_ru = {"metaphorical": "переносное", "literal": "прямое"}

    blocks = []
    for record in poems(args.poems):
        if record.id not in own["poems"]:
            continue
        columns = "".join(
            f'<div class="col"><h4>{title}</h4>{figures(record.text, result)}</div>'
            for title, result in (
                (name, own["poems"].get(record.id)),
                ("gpt-4o-mini", gpt_mini.get(record.id)),
                ("Claude", claude.get(record.id)),
            )
        )
        blocks.append(
            f'<section class="card"><h3>{html.escape(record.title)}</h3>'
            f'<div class="cols">{columns}</div></section>'
        )

    rows = []
    for record in quotations(args.quotations):
        if record["id"] not in own["direct"] and record["id"] not in own["quotes"]:
            continue
        gold = usage_ru[record["usage_type"]]
        direct = own["direct"].get(record["id"], {"error": "нет прогона"})
        usage, reason = direct_answer(direct)
        answer = usage_ru.get(usage, "нет ответа")
        reference = usage_ru.get(gpt_direct.get(record["id"], {}).get("usage"), "—")

        def cell(value, gold=gold):
            css = "ok" if value == gold else "bad" if value in usage_ru.values() else ""
            return f'<td class="{css}">{html.escape(value)}</td>'

        quote = record["text"]
        marked = (
            html.escape(quote[: record["start"]])
            + f"<mark>{html.escape(quote[record['start'] : record['end']])}</mark>"
            + html.escape(quote[record["end"] :])
        )
        mine = own["quotes"].get(record["id"])
        if mine and "error" not in mine:
            found = ", ".join(html.escape(s["text"]) for s in mine["metaphors"]) or "ничего"
        else:
            found = error_ru(mine["error"]) if mine else "нет прогона"
        rows.append(
            f"<tr><td><b>{html.escape(record['target'])}</b><br>"
            f'<span class="quote">{marked}</span></td><td>{gold}</td>'
            f"{cell(reference)}{cell(answer)}"
            f'<td class="muted">{html.escape(reason)}{"" if usage else raw_output(direct)}</td>'
            f"{cell(headword_marked(record, mine))}"
            f"{cell(headword_marked(record, gpt_two_stage.get(record['id'])))}"
            f'<td class="muted">{found}</td></tr>'
        )

    records = {r["id"]: r for r in quotations(args.quotations)}

    def summary_of(run: dict) -> str:
        def accepted(kind):
            return f"{sum('error' not in r for r in run[kind].values())} из {len(run[kind])}"

        answers = {i: direct_answer(r)[0] for i, r in run["direct"].items()}
        correct = sum(u == records[i]["usage_type"] for i, u in answers.items() if i in records)
        hits = [
            headword_marked(records[i], r) == usage_ru[records[i]["usage_type"]]
            for i, r in run["quotes"].items()
            if i in records and "error" not in r
        ]
        return (
            f"<ul><li>Анализ стихов Абая: ответ принят в {accepted('poems')}.</li>"
            f"<li>Анализ словарных цитат: ответ принят в {accepted('quotes')}, из них "
            f"заглавное слово оценено как в словаре в {sum(hits)}.</li>"
            f"<li>Прямой вопрос: ответила по существу в "
            f"{sum(u is not None for u in answers.values())} из {len(answers)}, из них совпало "
            f"со словарём {correct}.</li></ul>"
        )

    summary = summary_of(own)
    if args.lenient and any(strict.values()):
        summary = (
            f"<h4>Мягкая проверка формата</h4>{summary}"
            f"<h4>Строгая проверка (как на сайте)</h4>{summary_of(strict)}"
        )

    body = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} против gpt-4o</title><style>
:root{{--bg:#fafaf7;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e3e1da;--mark:#ffe28a;--ok:#dff3e1;--bad:#fbe0dc}}
@media (prefers-color-scheme:dark){{:root{{--bg:#191917;--fg:#ecebe6;--muted:#a3a29b;--card:#23231f;--line:#3a3934;--mark:#7a6420;--ok:#1f3a24;--bad:#4a2420}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:1200px;padding:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:16px 0}}
.cols{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
mark{{background:var(--mark);color:inherit;border-radius:3px;padding:0 2px}}
.muted{{color:var(--muted);font-size:13px}} .error{{color:#c0392b}} .poem{{white-space:normal}} pre{{white-space:pre-wrap;font-size:12px}}
.count{{font-weight:600;margin:4px 0}} ul{{padding-left:18px}} li{{margin-bottom:6px}}
table{{border-collapse:collapse;width:100%;background:var(--card)}} td,th{{border:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left}}
td.ok{{background:var(--ok)}} td.bad{{background:var(--bad)}} .tbl{{overflow-x:auto}} .quote{{font-size:14px}}
</style></head><body>
<h1>{name} в работе: что она находит на самом деле</h1>
<p>Прогон на видеокарте (основа в 4 битах), тот же анализ, что на сайте, но без
второго этапа gpt-4o.{LENIENT_NOTE if args.lenient else ""} Для стихов Абая эталона нет: рядом разметка gpt-4o-mini и Claude
(модельная, не gold). Для словарных цитат эталон — помета словаря «ауыс.».</p>
<div class="card"><h3>Итог</h3>{summary}</div>
<h2>1. Стихи Абая: какие фигуры находит каждая модель</h2>{"".join(blocks) or "<p>нет данных</p>"}
<h2>2. Словарные цитаты: прямое или переносное?</h2>
<p class="muted">Зелёным — совпало со словарём, красным — нет. «Прямой вопрос»: модели называют слово
и спрашивают о нём; KazLLM здесь отвечает свободным текстом с объяснением. «Обычный анализ»:
модель сама ищет фигуры во всей цитате; считается, отметила ли она заглавное слово.</p>
<div class="tbl"><table><thead><tr><th>Слово и цитата</th><th>Словарь</th>
<th>gpt-4o, прямой вопрос</th><th>{name}, прямой вопрос</th><th>Объяснение {name}</th>
<th>{name}, обычный анализ</th><th>gpt-4o, двухшаговый</th><th>Что отметила {name}</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<p class="muted">Цитаты из «Қазақ әдеби тілінің сөздігі» — только для внутренней оценки, не публиковать.</p>
</body></html>"""
    path = ROOT / f"compare-{tag(args)}.html"
    path.write_text(body, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "html"])
    parser.add_argument("--model", default="issai/LLama-3.1-KazLLM-1.0-8B")
    parser.add_argument("--poems", type=int, default=12)
    parser.add_argument("--quotations", type=int, default=30)
    parser.add_argument("--lenient", action="store_true", help="replace out-of-list values")
    args = parser.parse_args()
    # The page needs the gpt-4o and Claude runs, which are not shipped to Kaggle.
    if args.command == "run":
        run(args)
    else:
        print(page(args))


if __name__ == "__main__":
    main()

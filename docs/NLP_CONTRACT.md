# Контракт NLP для Армана и Никиты

Версия таксономии: **2.0** (добавлены поля ТЗ п. 4.1; все новые поля необязательны,
результаты версии 1.0 читаются без изменений). Это реализованное предложение для согласования команды;
файл распределения задач не задавал конкретный справочник типов и областей.
Публичные поля стартового бэкенда сохранены.

## Метки

| `label` | Значение | Положительная метка XLM-R |
|---|---|---|
| `metaphor` | Междоменный перенос без более конкретного типа | Да |
| `personification` | Человеческое действие/свойство у нечеловеческого объекта | Да |
| `simile` | Явное образное сравнение | Нет, отдельная вспомогательная фигура |
| `metonymy` | Перенос по смежности | Нет |
| `idiom` | Устойчивое выражение без отдельно обоснованной метафоры | Нет |

BIO: `O`, `B-METAPHOR`, `I-METAPHOR`. Олицетворение имеет приоритет над общей
метафорой. Идиома, для которой обоснован метафорический перенос, получает
`metaphor` или `personification`, а не вторую перекрывающуюся аннотацию.
Явные сравнения можно включить в отдельный эксперимент позже, изменив версию
таксономии и пересчитав метрики. Нельзя незаметно смешивать определения задачи.

## Смысловые области

`nature`, `water`, `fire`, `light`, `darkness`, `plant`, `animal`, `body`,
`person`, `object`, `space`, `motion`, `journey`, `time`, `life`, `death`,
`emotion`, `love`, `mind`, `society`, `spirituality`, `other`, `unknown`.

`source_domain` — образ, из которого берётся перенос; `target_domain` — то,
что через него описывается. Для «өмір өзені» (синтетический пример) это
`water → life`. Выбирать наиболее конкретную подходящую область: `water`
вместо `nature`. `other` — понятная область вне справочника; `unknown` —
по тексту область определить нельзя. Подробные определения — в инструкции разметки.

## Формат результата

`contracts/analysis-result.schema.json` — схема результата модуля.
`contracts/llm-output.schema.json` — более строгая схема ответа LLM без поля
версии модели: достоверную версию добавляет код. Список областей для новых
результатов проверяет NLP-модуль. В публичной схеме API области оставлены строками,
чтобы старые записи БД с произвольными значениями продолжали читаться.

```json
{
  "language": "kk",
  "model_version": "lexical-demo-v1",
  "metaphors": [{
    "text": "Өмір өзені",
    "start": 0,
    "end": 10,
    "label": "metaphor",
    "source_domain": "water",
    "target_domain": "life",
    "confidence": 0.5,
    "rationale": "Lexical candidate; context requires human verification."
  }],
  "needs_review": true,
  "warnings": ["Lexical baseline has limited coverage; confidence is not calibrated."]
}
```

Исходный текст примера: `Өмір өзені тоқтамай ағады.`. Это искусственный пример,
а не цитата из произведения. Это результат NLP-модуля, а не HTTP-ответ на отправку.
Текущий API возвращает `202` с `analysis_id`, `status=queued` и `status_url`.
После завершения `GET status_url` возвращает этот NLP-объект внутри `result`.
Готовые запросы, ответы очереди (`*.response.json`) и результаты завершённых заданий
(`*.completed.json`) для обоих языков — в `contracts/examples/`.

### Поля ТЗ (версия 2.0)

| Поле ТЗ | Поле результата | Примечание |
|---|---|---|
| Entity | `metaphors[].entity`, `candidates[].text` | Слово-образ внутри выражения |
| Type | `entity_type` | `plant`, `animal`, `natural_phenomenon`, `landscape`, `celestial`, `body`, `person`, `artifact`, `abstract`, `other` |
| Context_Sentence | `metaphors[].context_sentence` | Строка или предложение исходного текста; вычисляется кодом |
| Usage_Type | `metaphors[].usage_type`, `candidates[].usage_type` | `metaphorical` / `literal`; `null` у кандидата — ещё не классифицирован |
| Source_Domain / Target_Domain | `source_domain` / `target_domain` | Справочник областей выше |
| Semantic_Label | `metaphors[].semantic_label` | «благородный муж», «хитрость»… |
| — | `metaphors[].sentiment` | `positive` / `neutral` / `negative` |
| Evidence_Reasoning | `metaphors[].rationale`, `candidates[].reasoning` | При CoT включает шаги MIP |

`candidates` — результат модуля B (словарь-ограничение и модель) с решением модуля C.
`method` — запись воспроизводимости: стратегия промпта, хеш промпта, T и top-p,
фактически применённые провайдером, версия словаря, документы RAG.
Экспорт в именах полей ТЗ: `GET /api/v1/analyses/{id}/export?format=tz` (JSON) или
`format=csv` (те же колонки). Схемы ответа LLM: `contracts/llm-output.schema.json`
и `contracts/llm-output-cot.schema.json`.

### Границы

- `start` включается, `end` не включается; отсчёт с нуля.
- Единица — Unicode code point, как индекс Python `str`. Это не байты и не UTF-16.
- Обязательно `original_text[start:end] == span.text`.
- Нельзя менять пробелы, регистр, пунктуацию, переносы строк или нормализацию Unicode
  после получения текста для анализа. Новая версия текста требует новой разметки.
- Вложенные и пересекающиеся фрагменты в версии 1 не поддерживаются.
- В JavaScript: `Array.from(originalText).slice(start, end).join("")`.
  Обычный `originalText.slice(start, end)` ошибается после emoji и иероглифов вне BMP.

`confidence` — технический score, пока без калибровки. У baseline он постоянный,
у LLM это самооценка, у XLM-R — средняя вероятность выбранных BIO-меток,
у гибрида при совпадении границ — минимум двух оценок. Числа между моделями
не сопоставимы напрямую. Все текущие результаты требуют проверки человека.
`needs_review` и `warnings` добавлены с defaults: старые сохранённые ответы читаются.

### Точки интеграции

```python
from app.services.analyzer import analyze_text
result = analyze_text("Өмір өзені тоқтамай ағады.", "kk")
payload = result.model_dump(mode="json")
```

Для самостоятельной работы без сервера и БД:

```python
from app.nlp.baseline import LexicalDetector
from app.nlp.pipeline import MetaphorPipeline
pipeline = MetaphorPipeline(LexicalDetector())
result = pipeline.analyze("我的心海泛起波浪。", "zh")
```

Метод `CrossLanguageMatcher.compare(queries, candidates, k)` возвращает
`query_id`, `candidate_id`, cosine `similarity`, `rank`. Идентификаторы задаёт
вызывающая сторона. Результат не включает выдуманную «уверенность культурного сходства».
Текущий HTTP `/compare` агрегирует частоты по сохранённым анализам; семантический
поиск через embeddings остаётся отдельной точкой интеграции. Для подсветки
загруженных документов Никите понадобится именно
извлечённый сервером текст; текущий ответ `/analyze/file` его не возвращает.

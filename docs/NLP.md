# NLP часть Арслана

Модуль обнаруживает метафорические выражения в китайском и казахском тексте и
готовит кандидатов для межъязыкового сопоставления. Здесь находится код нашей части:
корпус, разметка, baseline, LLM, обучение и инференс XLM-R, классификация областей и оценка.
Бэкенд вызывает прежнюю функцию `app.services.analyzer.analyze_text(text, language)`.

## Что готово и что нужно получить

Код и демонстрационные примеры готовы к запуску. Настоящий корпус, согласование
разметки носителями языка, обученные на нём веса и научные результаты ещё нужны.
`data/examples/synthetic.jsonl` содержит 12 искусственных примеров для проверки кода.
Даже поле `annotation_status=gold` в этих тестовых записях не означает человеческую
разметку: `synthetic=true` запрещает использовать их обычной командой обучения.

| Этап из ТЗ | Реализованный инструмент | Что остаётся в исследовании |
|---|---|---|
| 1–2: постановка и схема | Этот план, `RESEARCH.md`, JSON Schema, реестр источников | Утвердить исследовательские вопросы и проверить источники |
| 3: корпус | Проверка JSONL, очистка, поиск дубликатов, разделение по произведению | Собрать и проверить реальный корпус |
| 4–6: разметка и LLM | Инструкция, Label Studio config, импорт/экспорт, OpenAI/Ollama | Независимая разметка и арбитраж Арслана |
| 7–8: baseline и XLM-R | Словарь, Precision/Recall/F1, train/inference BIO | Обучить и оценить на gold-наборе |
| 9: типы и области | Обучаемые TF-IDF + LogisticRegression классификаторы | Сравнить с LLM; при необходимости заменить модель |
| 10: гибрид | Слияние XLM-R и LLM, сохранение разногласий | Выбрать порог по validation; оценить калибровку |
| 11–12: сопоставление | multilingual-e5, cosine ranking, Recall@k | Разметить релевантные пары и проверить качество по направлениям |
| 13–15: интеграция и выводы | Единый модуль, JSON-примеры, тесты | Реальные веса, замеры скорости, финальная оценка |

## Запуск в Windows / PyCharm

Открыть корень `justFriends` как проект. Выбрать Python 3.11 или новее.
Для текущей проверки создана `.venv` с доступом к уже установленному PyTorch.
Для чистой воспроизводимой установки можно создать обычную отдельную среду:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,nlp]"
.\.venv\Scripts\python.exe -m app.nlp demo
```

`demo` работает без интернета, ключей и весов моделей. Результаты:
`runs/demo/predictions.json` и `runs/demo/metrics.json`.
Минимальный набор для baseline/LLM: `pip install -e ".[dev]"`.
`.[nlp]` нужен для обучения, embeddings и проверки нейросетевого пути.
Версии, реально использованные при проверке, записаны в `docs/NLP_VERIFICATION.md`.

Запускать команды ниже из корня репозитория. В PyCharm можно создать Python-конфигурацию
с **Module name** `app.nlp`, **Parameters** `demo`, **Working directory** — корень проекта.

## Режимы анализа

| `NLP_BACKEND` | Назначение | Требования |
|---|---|---|
| `baseline` | Простой словарный поиск для демонстрации и нижней точки сравнения | Без моделей и ключей |
| `openai` | Предварительная разметка через существующий Responses API | `OPENAI_API_KEY`, доступный `OPENAI_MODEL` |
| `ollama` | LLM через Ollama | Запущенная Ollama и уже установленная модель в `OLLAMA_MODEL` |
| `xlmr` | Локальный обученный BIO-детектор | `XLMR_MODEL_PATH` с нашим checkpoint |
| `hybrid` | XLM-R и дополнительная проверка всего текста LLM | Checkpoint и настроенный LLM-провайдер |

По умолчанию остаётся `openai`. Название модели из стартового бэкенда сохранено;
её доступность в вашем API-аккаунте не проверялась. Укажите доступную модель с
поддержкой Structured Outputs. Ключи хранить в `.env`, который исключён из Git.

```powershell
$env:NLP_BACKEND = "baseline"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Вызовы `/api/v1/analyze` и `/api/v1/analyze/file` используют выбранный режим.
Они возвращают `202` с `status_url`; результат нужно читать из поля `result` при
`GET status_url` после статуса `completed`. Ошибка модели или её конфигурации
завершает задание со статусом `failed`. Подробности — в `docs/API_CONTRACT.md`.
После смены настроек перезапустить процесс: модель кешируется в памяти.
Нельзя запускать несколько больших моделей в каждом из многочисленных API workers
без учёта GPU-памяти. Очередь и инфраструктуру интегрирует Арман.

Анализ файла без запуска сервера:

```powershell
python -m app.nlp analyze --text-file poem.txt --language kk --backend baseline --output runs/result.json
```

LLM-адаптеры требуют строгий JSON, проверяют язык, словарь областей, границы и
совпадение текста. Незавершённые, выдуманные и пересекающиеся фрагменты отклоняются.
Текст передаётся как данные; команды, написанные внутри стихотворения, не являются
инструкциями анализатору. Ошибочный ответ не заменяется пустым успешным результатом.
Ollama получает явный `num_ctx` из `OLLAMA_CONTEXT_WINDOW` (по умолчанию 8192),
лимит генерации 2048 и консервативную предварительную проверку объёма по UTF-8 байтам
с резервом на ответ. Для длинного произведения увеличить контекст в пределах возможностей
модели и памяти либо явно подготовить меньший контекст. Ответ, оборванный лимитом, отклоняется.

## Данные и обучение

1. Собрать JSONL по `contracts/corpus.schema.json`, заполнить источник и лицензию.
2. Проверить и очистить **до разметки**:

```powershell
python -m app.nlp validate data/raw/corpus.jsonl
python -m app.nlp clean data/raw/corpus.jsonl --output data/processed/corpus.jsonl
python -m app.nlp label-studio-export data/processed/corpus.jsonl --output runs/tasks.json
```

3. Импортировать задачи в Label Studio с `annotation/label_studio.xml`.
   Инструкция — `annotation/GUIDELINES.md`. Каждое произведение размечать целиком,
   отрицательные примеры тоже отмечать как просмотренные.
4. Выгрузить человеческую разметку. Обычный импорт даёт `draft`:

```powershell
python -m app.nlp label-studio-import runs/annotations.json --output data/processed/draft.jsonl
```

После независимой проверки и разрешения разногласий использовать
`--adjudicator Arslan`. В экспортируемом задании оставить одну выбранную итоговую
аннотацию. Две конкурирующие аннотации импортёр намеренно не выбирает за человека.
`predictions` LLM игнорируются и не могут превратиться в gold.

5. Разделить gold по `work_id`: разные фрагменты, варианты и переводы одного оригинала
   должны иметь общий `work_id`. Проверить баланс языков и классов в полученных файлах;
   малый корпус нельзя считать репрезентативным только из-за фиксированного seed.

```powershell
python -m app.nlp split data/gold/corpus.jsonl --output data/gold/splits
python -m app.nlp train --train data/gold/splits/train.jsonl --validation data/gold/splits/validation.jsonl --output models/xlmr
python -m app.nlp train-attributes --train data/gold/splits/train.jsonl --output models/attributes
```

Обучение требует gold, проверенную лицензию и непересекающиеся произведения в train/validation.
Первая загрузка базовой XLM-R требует интернета. Весам нужен отдельный пустой каталог.
Сохраняется checkpoint с лучшим exact-span F1 на validation и `experiment.json`
с seed, настройками, хешами данных и историей. Тестовая выборка в обучении не используется.
Обычный XLM-R checkpoint без нашей BIO-головы не принимается как обученный детектор.
Скользящие окна покрывают весь текст; границы gold, которые разрезают токен модели,
вызывают ошибку и требуют пересмотра разметки. Они не сдвигаются автоматически.

Для классификации областей при `NLP_BACKEND=xlmr` задать
`ATTRIBUTE_MODEL_PATH=models/attributes`. Это обучаемый baseline на символьных
признаках; он не заменяет оценку межъязыкового переноса. Загрузка `.joblib`
допускается только из собственных доверенных экспериментов.

## Оценка

```powershell
python -m app.nlp predict data/gold/splits/test.jsonl --backend xlmr --output runs/xlmr-test.json
python -m app.nlp evaluate --gold data/gold/splits/test.jsonl --predictions runs/xlmr-test.json --output runs/xlmr-metrics.json
python -m app.nlp agreement runs/annotator-a.jsonl runs/annotator-b.jsonl --output runs/agreement.json
```

`metaphor_detection` — Precision/Recall/F1 по точным границам метафор и олицетворений.
`typed_figures` — точные границы и тип всех пяти фигур. Отчёт содержит `all`, `zh`, `kk`.
Ошибки областей и матрицы ошибок типов считаются отдельно на совпавших границах;
это условная оценка, её нельзя выдавать за end-to-end точность классификации.
Нельзя удалять отрицательные тексты и отсутствующие предсказания из знаменателя.
Согласие: exact-span F1 и бинарная Cohen kappa по символам; при вырожденном случае
kappa равна `null`. Это не kappa по словам и не полная оценка всех атрибутов.

## Межъязыковое сравнение

```powershell
python -m app.nlp compare --queries contracts/examples/compare-queries.json --candidates contracts/examples/compare-candidates.json --k 5 --output runs/comparison.json
python -m app.nlp recall-at-k --relevance runs/relevance.json --rankings runs/rankings.json --k 5
```

Первый `compare` загружает multilingual-e5-base. Можно передать локальный путь через
`EMBEDDING_MODEL`. На обеих сторонах симметричного сравнения используется `query: `,
как указано в [карточке E5](https://huggingface.co/intfloat/multilingual-e5-base).
Векторы нормализуются, кандидаты фильтруются по другому языку; текст, превышающий
лимит модели, отклоняется с просьбой явно сократить контекст.

`relevance.json`: `{"zh-1": ["kk-1", "kk-3"]}`;
`rankings.json`: `{"zh-1": ["kk-2", "kk-1", "kk-3"]}`.
Recall@k усредняется по запросам и учитывает долю всех релевантных кандидатов,
а не только наличие хотя бы одного попадания. Считать отдельно zh→kk и kk→zh.
Сходство embeddings не доказывает общность культурного смысла; пары проверяют люди.
Текущий HTTP `/compare` возвращает агрегированную статистику. Для семантического
поиска Арман может подключить `CrossLanguageMatcher.compare()` отдельно,
используя `contracts/comparison-*.schema.json`.

## Проверки

```powershell
python -m pytest -q --basetemp=runs/pytest
python -m ruff check app/nlp app/schemas scripts tests
python -m scripts.export_nlp_contracts
```

Нейросетевой тест создаёт крошечную случайную XLM-R локально, выполняет обучение,
сохранение, загрузку и инференс. Он проверяет код, а не качество реальной XLM-R.
API-адаптеры LLM проверяются на контролируемых ответах без платных запросов.

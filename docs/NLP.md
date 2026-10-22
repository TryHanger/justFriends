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
Создать отдельную среду и поставить зависимости (torch лучше ставить первым,
CPU-сборка легче и не требует CUDA):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -e ".[dev,nlp]"
.\.venv\Scripts\python.exe -m app.nlp demo
```

`demo` работает без интернета, ключей и весов моделей. Результаты:
`runs/demo/predictions.json` и `runs/demo/metrics.json`.
Минимальный набор для baseline/LLM: `pip install -e ".[dev]"`.
`.[nlp]` нужен для обучения, embeddings и проверки нейросетевого пути.

Для сопоставления (`compare`) нужна модель `intfloat/multilingual-e5-base` (~1 ГБ).
Она скачивается с Hugging Face один раз при первом запуске; скачать заранее и проверить:

```powershell
.\.venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer; print(SentenceTransformer('intfloat/multilingual-e5-base').encode(['query: test']).shape)"
```

Должно вывести `(1, 768)`. Если Hugging Face недоступен, задать `$env:HF_ENDPOINT="https://hf-mirror.com"`
или скачать модель в папку (`hf download intfloat/multilingual-e5-base --local-dir models/e5-base`)
и указать `EMBEDDING_MODEL=models/e5-base` в `.env`.
Версии, реально использованные при проверке, записаны в `docs/NLP_VERIFICATION.md`.

Запускать команды ниже из корня репозитория. В PyCharm можно создать Python-конфигурацию
с **Module name** `app.nlp`, **Parameters** `demo`, **Working directory** — корень проекта.

## Соответствие ТЗ

| Требование ТЗ | Где реализовано |
|---|---|
| Модуль A: препроцессинг, токенизация | `clean` (NFC, вариантные знаки, редакторские пометы, `--verse-lines`, латиница в казахских словах), `fertility`, `train-tokenizer` |
| Модуль B: кандидаты с soft lexicon | `app/nlp/lexicon.py`, `data/lexicons/{zh,kk}.json` |
| Модуль C: literal vs metaphorical, CoT, MIP/MIPVU | `app/nlp/prompts.py` (компонент `cot`), `candidates[].usage_type` |
| Модуль D: метки, тональность, домены | поля `semantic_label`, `sentiment`, `source/target_domain`; `/compare` |
| Модуль E: экспертная проверка | Label Studio v2.0, `agreement` (Fleiss/Cohen), `needs_review` |
| п. 4.1 параметры и формат | `LLM_TEMPERATURE=0.2`, `LLM_TOP_P=0.95`, экспорт `format=tz` |
| Prompting / RAG / Fine-tuning | стратегии `zero_shot`, `few_shot`, `cot`, `rag`, `lexicon`; `build-ift`, `finetune`, backend `hf` |
| Модели | OpenAI, Claude (`anthropic`), Qwen-2.5 / LLaMA-3.1 (Ollama или `hf`), SozKZ (`hf`) |
| H1–H3, метрики п. 6 | `experiment`, `evaluate --bootstrap`, `fertility`, `probe` |

## Режимы анализа

| `NLP_BACKEND` | Назначение | Требования |
|---|---|---|
| `baseline` | Простой словарный поиск для демонстрации и нижней точки сравнения | Без моделей и ключей |
| `openai` | Предварительная разметка через существующий Responses API | `OPENAI_API_KEY`, доступный `OPENAI_MODEL` |
| `anthropic` | Claude через Messages API со структурированным выводом | `ANTHROPIC_API_KEY` или профиль `ant auth`, `ANTHROPIC_MODEL` |
| `hf` | Локальная модель Transformers, в том числе с LoRA-адаптером | `HF_MODEL`, при необходимости `HF_ADAPTER`; `.[nlp,finetune]` |
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

Стратегия LLM задаётся `LLM_PROMPT_STRATEGY` (по умолчанию `few_shot+cot+rag+lexicon`)
или `--strategy` в CLI: `zero_shot` либо комбинация `few_shot`, `cot`, `rag`, `lexicon`
через `+`. База знаний RAG — `data/knowledge/*.jsonl` (MIP/MIPVU, комментарии Ван И,
образы жырау); новые комментарии добавлять в том же формате с полем `source`.

```powershell
python -m app.nlp analyze --text-file poem.txt --language zh --backend anthropic --strategy cot+lexicon --output runs/r.json
```

### Двухэтапный режим для казахского

На словарном наборе (цитаты из 15-томного толкового словаря с пометой «ауыс.» и без неё)
обычный однопроходный анализ — LLM ищет все фигуры во всём тексте — согласуется со словарём
лишь на уровне Cohen κ≈0.11 (gpt-4o-mini). Та же модель на прямой вопрос «слово X здесь
употреблено в прямом или переносном смысле?» даёт κ 0.29, gpt-4o — 0.45, gpt-5.6-terra — 0.51.
Узкое место — обнаружение за один проход, а не знание языка. Поэтому для языков из
`NLP_TWO_STAGE_LANGUAGES` (по умолчанию `kk`) анализ идёт в два этапа:

1. Как раньше: кандидаты из soft lexicon (`CandidateExtractor`) и из ответа LLM
   (фигуры и `literal_candidates`), объединённые `merge_candidates`.
2. Каждый кандидат текста получает прямой вопрос модели `NLP_USAGE_MODEL` (по умолчанию
   `gpt-4o`) у провайдера `NLP_USAGE_BACKEND` (по умолчанию `openai`) — тот же промпт и схема,
   что в `scripts/eval_kk_usage_direct.py` (общая реализация в `app/nlp/usage.py`), с
   требованием объяснять по-русски. Один кандидат — ровно измеренный вопрос; несколько
   кандидатов одного текста идут пачками до 8 в одном запросе. Температура 0; если модель её
   не принимает, используется декодирование провайдера (`temperature: null` в записи).

Решение второго этапа записывается в `candidates[].usage_type` и `reasoning`. Кандидат,
признанный переносным и не пересекающий существующую фигуру, становится новой фигурой
(`label=metaphor`, `entity` = слово, домены `unknown`, объяснение второго этапа,
`confidence=0.5` — заглушка: прямой вопрос не даёт самооценки). Если головное слово фигуры
первого этапа признано буквальным, фигура не удаляется: добавляется предупреждение, и
результат остаётся на экспертной проверке. Объяснения проходят ту же проверку на русский
язык, калибровка применяется после — только к фигурам первого этапа (добавленные перечислены
в `method.two_stage.added`, их пропускает и `scripts/calibrate_llm.py`).

`method.two_stage` содержит модель, число кандидатов и решений, добавленные и спорные фигуры,
число неудавшихся запросов и токены второго этапа (`usage`; токены первого этапа и перевода —
в `method.usage`). Ошибка запроса второго этапа не отменяет анализ: решения первого этапа
сохраняются, предупреждение сообщает, сколько кандидатов не проверено.

Режим действует только для LLM-бэкендов (`openai`, `anthropic`, `ollama`, `hf` и LLM-часть
`hybrid`) и только для перечисленных языков; `zh` по умолчанию идёт в один проход. Включение
и выключение — через `.env` или переменные окружения:

```powershell
# по умолчанию: казахский в два этапа, второй этап — gpt-4o через OpenAI
$env:NLP_TWO_STAGE_LANGUAGES = "kk"
$env:NLP_USAGE_MODEL = "gpt-5.6-terra"     # сильнее и дороже
$env:NLP_TWO_STAGE_LANGUAGES = ""          # выключить (прежний однопроходный режим)
```

Для бэкендов `anthropic`, `ollama`, `hf` второй этап по умолчанию тоже идёт в OpenAI и
требует `OPENAI_API_KEY`; без ключа сборка конвейера сообщает об этом. Можно указать
`NLP_USAGE_BACKEND=anthropic` или `ollama` с моделью этого провайдера в `NLP_USAGE_MODEL`,
либо выключить режим. Сравнение с однопроходным режимом и с прямым вопросом на словарном
наборе — `scripts/eval_kk_usage.py` (раздел `two_stage` отчёта) и
`scripts/eval_kk_usage_direct.py`.

`NLP_USAGE_ALL_WORDS` (по умолчанию `true`): второй этап спрашивает и о каждом знаменательном
казахском слове, которого не покрыли кандидаты первого этапа (служебные слова отбрасываются
списком `KAZAKH_FUNCTION_WORDS` в `app/nlp/usage.py`). Слова, признанные буквальными, в таблицу
кандидатов не попадают; признанные переносными становятся фигурами. На словарном наборе
(160 цитат, второй этап gpt-4o) это поднимает согласие со словарём с κ 0.24 до 0.38 и полноту
с 0.61 до 0.90 при росте ложных срабатываний с 38% до 53%; токены второго этапа — около
156k входных и 76k выходных на 160 цитат.

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
Ollama получает явный `num_ctx` из `OLLAMA_CONTEXT_WINDOW` (по умолчанию 16384),
лимит генерации 2048 и консервативную предварительную проверку объёма по UTF-8 байтам
с резервом на ответ. Для длинного произведения увеличить контекст в пределах возможностей
модели и памяти либо явно подготовить меньший контекст. Ответ, оборванный лимитом, отклоняется.

### Типы строф 賦 / 比 / 興 (Шицзин)

Для китайского текста любой режим дополнительно размечает строфы по классификации
Чжу Си (詩經集傳): 賦 — описание, 比 — сравнение, 興 — образ-зачин. Модель
`models/zhuxi-stanza-sikuroberta-v1` (SikuRoBERTa, 968 строф; обучение —
`scripts/train_stanza_classifier.py`) задаётся `STANZA_MODEL_PATH`; пустое значение
отключает разметку. Код — `app/nlp/stanza.py`. Строфы разделяются пустой строкой, текст
без пустых строк — одна строфа; упрощённые знаки переводятся в полные через OpenCC
(`opencc-python-reimplemented` в extra `nlp`). Результат — поле `stanzas` (`text`,
`start`, `end`, `label`, `probabilities`), версия модели — `method.stanza_model`.
Без папки модели или без torch/transformers/opencc шаг молча пропускается, а `stanzas`
остаётся пустым. Качество (5-fold CV по стихотворениям): macro-F1 0.55, κ с Чжу Си 0.43,
для 比 F1 лишь 0.24, поэтому интерфейс показывает метку как подсказку модели с вероятностью.

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
python -m app.nlp agreement runs/annotator-a.jsonl runs/annotator-b.jsonl runs/annotator-c.jsonl --output runs/agreement.json
```

`metaphor_detection` — Precision/Recall/F1 по точным границам метафор и олицетворений.

Диагностические метрики (`app/nlp/quality.py`) объясняют, *почему* F1 такой:
`overlap_detection` и `char_detection` — нашла ли модель метафору при неточных границах;
`document_detection` с `false_positive_rate` — ложные тревоги на текстах без метафор
(нужны размеченные отрицательные примеры); `text_fields` — chrF и точное совпадение
темы, основания и семантической метки; `tenor_localization` — позиция темы в тексте;
`calibration` — ECE, Brier и точность/покрытие по порогам уверенности, чтобы выбрать,
что отправлять экспертам; `by_genre` — качество по жанрам (проза CMDAG и поэзия);
`reliability` — сбои, пропущенные фрагменты и фактический расход токенов (`method.usage`).
Домен `unknown` в gold не засчитывается как правильный ответ.
`entity_extraction`, `usage_classification`, `semantic_labeling` — метрики ТЗ п. 6;
блок `tz_targets` сравнивает их с целями. `--bootstrap 1000` добавляет 95% интервалы
по произведениям. Метрики сущностей считаются на записях, где gold содержит `candidates`.
`typed_figures` — точные границы и тип всех пяти фигур. Отчёт содержит `all`, `zh`, `kk`.
Ошибки областей и матрицы ошибок типов считаются отдельно на совпавших границах;
это условная оценка, её нельзя выдавать за end-to-end точность классификации.
Нельзя удалять отрицательные тексты и отсутствующие предсказания из знаменателя.
Согласие: exact-span F1 и бинарная Cohen kappa по символам; при вырожденном случае
kappa равна `null`. Это не kappa по словам и не полная оценка всех атрибутов.

## Эксперименты по ТЗ

```powershell
# Корпуса
python -m app.nlp import-chinese-poetry chinese-poetry/楚辞/chuci.json --era "Warring States" --genre chuci --revision <commit> --output data/raw/chuci.jsonl
python -m app.nlp import-texts data/raw/kk_texts --metadata data/raw/kk_texts.csv --output data/raw/kk.jsonl
python -m app.nlp clean data/raw/chuci.jsonl --verse-lines --output data/processed/chuci.jsonl
# Сравнение методов на Golden Test Set (пример конфигурации: experiments/pilot.example.json)
python -m app.nlp experiment --config experiments/pilot.example.json --output runs/pilot
# H1: IFT-датасет и LoRA
python -m app.nlp build-ift data/gold/splits/train.jsonl --output data/ift/train.jsonl
python -m app.nlp build-ift data/gold/splits/validation.jsonl --output data/ift/validation.jsonl
python -m app.nlp finetune --train data/ift/train.jsonl --validation data/ift/validation.jsonl --base-model Qwen/Qwen2.5-7B-Instruct --output models/qwen-ift
# H2: фертильность токенизаторов и казахский BPE на 50K
python -m app.nlp fertility data/processed/kk.jsonl --language kk --tokenizers FacebookAI/xlm-roberta-base Qwen/Qwen2.5-7B-Instruct <SozKZ-id> --output runs/fertility-kk.json
python -m app.nlp train-tokenizer data/processed/kk.jsonl --language kk --vocab-size 50000 --output models/kk-bpe
# H3: послойный пробинг
python -m app.nlp probe data/gold/corpus.jsonl --model FacebookAI/xlm-roberta-base --output runs/probe-xlmr.json
```

`experiment` пишет для каждого запуска `predictions.json`, `failures.json`, `metrics.json`
и общие `summary.csv`/`summary.md` с флагами достижения целей ТЗ. Готовые запуски не
повторяются. `finetune` требует `pip install -e ".[nlp,finetune]"` и GPU для моделей 7B.
Идентификатор SozKZ на Hugging Face указать после проверки карточки модели.

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
HTTP `/compare` возвращает агрегированную статистику. `POST /api/v1/compare/semantic`
теперь вызывает `CrossLanguageMatcher` для выбранных завершённых анализов в обоих
направлениях. Для каждого фрагмента передаётся контекст до 120 символов до и после
него. Формат запроса и ответа описан в `docs/API_CONTRACT.md`.

Этот endpoint не заменяет человеческую проверку. Для научных выводов всё ещё нужны
лицензированный adjudicated gold-корпус и вручную проверенная выборка релевантных пар.

## Проверки

```powershell
python -m pytest -q --basetemp=runs/pytest
python -m ruff check app/nlp app/schemas scripts tests
python -m scripts.export_nlp_contracts
```

Нейросетевой тест создаёт крошечную случайную XLM-R локально, выполняет обучение,
сохранение, загрузку и инференс. Он проверяет код, а не качество реальной XLM-R.
API-адаптеры LLM проверяются на контролируемых ответах без платных запросов.


## Режим классической китайской поэзии

`NLP_CLASSICAL_ZH` (по умолчанию `true`) и `NLP_ALLEGORY_MODEL` (по умолчанию `gpt-4o-mini`),
`app/nlp/allegory.py`. Для китайских текстов, похожих на классические стихи (частица 兮 или
не меньше 75% строк по 3–7 иероглифов), после основного анализа модели задаётся прямой вопрос
в традиции комментария (王逸, 毛传, 朱熹): какие образы обозначают другое — государя,
достойных или клеветников, самого поэта, человеческую ситуацию за 興-зачином. Каждый образ, не
покрытый фигурой, добавляется с темой (`tenor`, что он обозначает) и русским пояснением;
уверенность 0.5 (калибровка её не трогает), анализ помечается для проверки. Кандидат с тем же
словом получает статус «переносное». Контекст — база комментариев Ван И (`data/knowledge`).

Проверка (`scripts/eval_wangyi_llm.py`, комментарий к проверяемому стихотворению убран):
такой вопрос находит 15 из 29 образов Ван И в «Чу Цы» против 2 у обычного анализа; точность не
измеряется, так как Ван И комментирует не каждый образ. Один дополнительный запрос
`gpt-4o-mini` на текст (≈2k входных токенов).

Классификатор строф 賦/比/興 применяется только к текстам в размере «Ши цзин» (не меньше 60%
строк по 4 иероглифа): для «Чу Цы» и танских стихов его метки не имеют смысла.

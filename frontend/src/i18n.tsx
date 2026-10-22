import { useContext } from 'react';
import { LanguageContext } from './LanguageContext';
import type { Language } from './LanguageContext';

export function useLanguage() { return useContext(LanguageContext); }

const ru: Record<string, string> = {
  'Analysis #': 'Анализ №', completed: 'Завершён', failed: 'Ошибка', queued: 'В очереди', processing: 'Выполняется',
  metaphor: 'Метафора', simile: 'Сравнение', personification: 'Олицетворение', metonymy: 'Метонимия', idiom: 'Идиома',
  nature: 'Природа', water: 'Вода', fire: 'Огонь', light: 'Свет', darkness: 'Тьма', plant: 'Растение', animal: 'Животное',
  body: 'Тело', person: 'Человек', object: 'Предмет', space: 'Пространство', motion: 'Движение', journey: 'Путешествие',
  time: 'Время', life: 'Жизнь', death: 'Смерть', emotion: 'Чувство', love: 'Любовь', mind: 'Сознание', society: 'Общество',
  spirituality: 'Духовность', other: 'Другое', unknown: 'Не определено',
  'Conf:': 'Уверенность:', 'Source:': 'Исходный образ:', 'Target:': 'Целевой образ:',
  'Metaphor Analyzer': 'Анализатор метафор', Analyses: 'Анализы', Compare: 'Сравнение',
  'New Analysis': 'Новый анализ', Language: 'Язык', 'Auto-detect': 'Определить автоматически',
  'Chinese (zh)': 'Китайский (zh)', 'Kazakh (kk)': 'Казахский (kk)', 'Poem Text': 'Текст стихотворения',
  'Paste poem text here...': 'Вставьте текст стихотворения…', OR: 'ИЛИ', 'Upload Document': 'Загрузить документ',
  Remove: 'Удалить', Analyze: 'Анализировать', 'Recent Analyses': 'Последние анализы',
  'Could not load analysis history. Check that the backend is available.': 'Не удалось загрузить историю. Проверьте доступность сервера.',
  'Analysis model': 'Модель анализа', 'Configured project model': 'Основная модель проекта',
  'Experimental Kazakh model (XLM-R)': 'Экспериментальная казахская модель (XLM-R)',
  'Experimental model': 'Экспериментальная модель',
  'Model catalog': 'Каталог моделей', 'Training records': 'Примеров обучения', unavailable: 'недоступна',
  'Archived baseline result': 'Архивный результат словарного baseline',
  'This analysis used the old dictionary baseline, not the current XLM-R or GPT model. Create a new analysis to use the current model.': 'Этот анализ выполнен старым словарным baseline, а не текущей XLM-R или GPT-моделью. Создайте новый анализ, чтобы использовать актуальную модель.',
  'Trained on a small Silver dataset. The result requires manual review and is not a Gold-quality measurement.': 'Обучена на небольшом Silver-наборе. Результат требует ручной проверки и не является Gold-метрикой качества.',
  'Please provide text or select a file.': 'Введите текст или выберите файл.', 'Failed to submit analysis.': 'Не удалось отправить текст на анализ.',
  'Text input': 'Ввод текста', 'No analyses yet. Submit your first poem!': 'Пока нет анализов. Отправьте первое стихотворение!',
  ID: 'ID', Source: 'Источник', Status: 'Статус', Date: 'Дата',
  'Compare Analyses': 'Сравнение анализов', 'Select at least one completed Chinese (zh) and one Kazakh (kk) analysis to compare metaphorical patterns.': 'Выберите хотя бы один завершённый анализ китайского (zh) и один казахского (kk) текста, чтобы сравнить метафорические образы.',
  'Select at least one Chinese (zh) and one Kazakh (kk) analysis.': 'Выберите хотя бы один анализ китайского (zh) и один казахского (kk) текста.',
  'Completed Analyses': 'Завершённые анализы', 'No completed analyses found.': 'Завершённых анализов пока нет.',
  'Select at least one Chinese and one Kazakh analysis.': 'Выберите хотя бы один китайский и один казахский анализ.',
  'Compare Selected': 'Сравнить выбранные', 'Comparison Results': 'Результаты сравнения',
  'Cross-language metaphor candidates': 'Межъязыковые кандидаты метафор',
  'Similarity ranks candidates; it does not prove cultural equivalence.': 'Сходство ранжирует кандидатов, но не доказывает культурную эквивалентность.',
  'No cross-language candidates to display.': 'Нет межъязыковых кандидатов для отображения.',
  Chinese: 'Китайский', Kazakh: 'Казахский', 'Total Metaphors': 'Всего метафор',
  'Top Sources': 'Частые исходные образы', 'Top Targets': 'Частые целевые образы', Types: 'Типы',
  metaphors: 'метафор', 'Average confidence': 'Средняя уверенность', 'Common source domains': 'Общие исходные образы',
  'shared image categories': 'общие категории образов', 'Type comparison': 'Сравнение типов', Type: 'Тип',
  'Cultural image comparison': 'Сопоставление культурных образов', Common: 'Общие', 'Chinese only': 'Только китайские',
  'Kazakh only': 'Только казахские', 'All matches': 'Все совпадения', 'High similarity': 'Высокое сходство',
  'Semantic comparison is temporarily unavailable; aggregate comparison is still shown.': 'Семантическое сравнение временно недоступно; обычное сравнение всё равно отображено.',
  'Select analyses and click compare to see results here.': 'Выберите анализы и нажмите «Сравнить», чтобы увидеть результат.',
  'Failed to compare.': 'Не удалось выполнить сравнение.',
  Library: 'Библиотека', 'Poetry Library': 'Библиотека поэзии', 'Upload books and build a searchable metaphor corpus.': 'Загружайте книги и создавайте корпус метафор для поиска и сравнения.',
  'Add a book': 'Добавить книгу', 'Title (optional)': 'Название (необязательно)', 'Author (optional)': 'Автор (необязательно)',
  'Upload and analyze': 'Загрузить и проанализировать', 'Books in the library': 'Книги в библиотеке', 'No books uploaded yet.': 'Книги ещё не загружены.',
  'Unknown author': 'Автор не указан', 'Select a book file first.': 'Сначала выберите файл книги.', 'Could not upload the book.': 'Не удалось загрузить книгу.', 'Could not load the library.': 'Не удалось загрузить библиотеку.',
  'Loading analysis...': 'Загрузка анализа…', 'Analysis not found or error loading it.': 'Анализ не найден или произошла ошибка загрузки.',
  'Go back': 'Вернуться', Metadata: 'Сведения', 'Created At': 'Создан', 'Model Version': 'Версия модели',
  'Text Input': 'Ввод текста', 'Analysis in progress...': 'Анализ выполняется…',
  "This may take a few moments. We'll automatically refresh.": 'Это может занять некоторое время. Страница обновляется автоматически.',
  'Analysis Failed': 'Ошибка анализа', 'An unknown error occurred during analysis.': 'Во время анализа произошла неизвестная ошибка.',
  'Analysis warnings': 'Предупреждения анализа', 'This analysis needs manual review.': 'Требуется ручная проверка анализа.',
  'Found Metaphors': 'Найденные метафоры', 'No metaphors detected in this document.': 'В документе метафоры не обнаружены.',
  Method: 'Метод', 'provider default decoding': 'декодирование по умолчанию провайдера',
  'Fields of the technical specification': 'Поля из ТЗ: Entity, Type, Context_Sentence, Usage_Type…', 'TZ format': 'Формат ТЗ',
  'Context:': 'Контекст:', 'Tenor:': 'Тема:', 'Ground:': 'Основание:', positive: 'позитивная', neutral: 'нейтральная', negative: 'негативная',
  'Entity candidates': 'Сущности-кандидаты', Entity: 'Сущность', Usage: 'Употребление',
  'Found by the soft lexicon and the model; each is judged literal or metaphorical in context.': 'Найдены словарём-ограничением и моделью; для каждой в контексте решено, прямое это употребление или переносное.',
  'Conventional reading / reasoning': 'Традиционное прочтение / обоснование',
  metaphorical: 'переносное', literal: 'прямое', unclassified: 'не решено',
  natural_phenomenon: 'Явление природы', landscape: 'Ландшафт', celestial: 'Небесное тело', artifact: 'Предмет', abstract: 'Абстракция',
  Sentiment: 'Тональность', 'Entity types': 'Типы сущностей', 'Domain pairs': 'Пары «источник → мишень»', 'Semantic labels': 'Семантические метки',
  Stanzas: 'Строфы', probability: 'вероятность',
  description: 'описание', comparison: 'сравнение', 'evocative image': 'образ-зачин',
  "Types follow Zhu Xi's classification (詩經集傳); labels are model suggestions, not expert annotation.": 'Типы строф даны по классификации Чжу Си (詩經集傳); метки — подсказки модели, а не экспертная разметка.',
};

export function tr(text: string, language: Language) { return language === 'ru' ? (ru[text] ?? text) : text; }

function calibrationSource(source: string) {
  if (source.startsWith('CMDAG')) return 'эталон CMDAG';
  if (source.startsWith('Kazakh explanatory dictionary')) return 'толковый словарь казахского языка';
  return source;
}

// Backend warnings are English and may contain numbers or offsets, so they are matched by pattern.
const warningPatterns: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^LLM preliminary annotation; confidence is self-reported and uncalibrated\.$/,
    () => 'Предварительная разметка LLM: уверенность — самооценка модели, она не откалибрована.'],
  [/^Confidence calibrated on (.+) \((\d+) figures\): the probability that a figure is correct\.$/,
    (m) => `Уверенность откалибрована на экспертных данных (${calibrationSource(m[1])}, ${m[2]} фигур): это вероятность того, что фигура найдена верно.`],
  [/^(\d+) of (\d+) figure\(s\) below the review threshold (\d+)%: check them first\.$/,
    (m) => `Проверьте в первую очередь фигуры с уверенностью ниже ${m[3]}%: ${m[1]} из ${m[2]}.`],
  [/^No figures found; models miss many figures, so review the text\.$/,
    () => 'Фигуры не найдены. Модели пропускают много фигур, поэтому проверьте текст вручную.'],
  [/^(\d+) (?:item|span)\(s\) omitted: the expression could not be aligned uniquely to the source text\.$/,
    (m) => `Пропущено фрагментов: ${m[1]} — выражение не удалось однозначно найти в исходном тексте.`],
  [/^(\d+) literal candidate\(s\) overlapped figurative spans and were dropped\.$/,
    (m) => `Отброшено буквальных кандидатов: ${m[1]} — они пересекались с найденными фигурами.`],
  [/^Provider rejected temperature\/top_p; its default decoding was used\.$/,
    () => 'Провайдер не принял temperature и top-p, использованы его параметры по умолчанию.'],
  [/^Lexical baseline has limited coverage; confidence is not calibrated\.$/,
    () => 'Словарный baseline покрывает мало случаев; уверенность не откалибрована.'],
  [/^Classical poetry mode \((.+)\): (\d+) image\(s\) read in the commentary tradition were added; recall on Wang Yi's Chu Ci images about 50%, precision not measured\.$/,
    (m) => `Режим классической поэзии (${m[1]}): добавлено образов, прочитанных в традиции комментария, — ${m[2]}. На образах Ван И из «Чу Цы» такой режим находит около половины; точность не измерялась, поэтому проверьте эти образы.`],
  [/^Classical poetry mode \((.+)\) failed; only stage-1 figures are shown\.$/,
    (m) => `Режим классической поэзии (${m[1]}) не сработал; показаны только фигуры основного анализа.`],
  [/^XLM-R does not determine source and target domains\.$/,
    () => 'XLM-R не определяет исходную и целевую области образа.'],
  [/^Token probabilities are uncalibrated; domains unknown\.$/,
    () => 'Вероятности XLM-R не откалиброваны; области не определены.'],
  [/^Detection and attribute scores are uncalibrated\.$/,
    () => 'Оценки обнаружения и атрибутов не откалиброваны.'],
  [/^LLM did not confirm span \[(\d+), (\d+)\)\.$/,
    (m) => `LLM не подтвердила фрагмент [${m[1]}, ${m[2]}).`],
  [/^LLM-only span \[(\d+), (\d+)\)\.$/,
    (m) => `Фрагмент [${m[1]}, ${m[2]}) нашла только LLM.`],
  [/^Conflicting LLM boundary \[(\d+), (\d+)\); kept primary boundary for manual adjudication\.$/,
    (m) => `Границы LLM [${m[1]}, ${m[2]}) расходятся с XLM-R; оставлены границы XLM-R для ручного решения.`],
  [/^(\d+) explanation\(s\) could not be translated into Russian\.$/,
    (m) => `Не удалось перевести на русский пояснений: ${m[1]}; показан исходный текст.`],
  [/^Candidate confidence is below review threshold ([\d.]+)\.$/,
    (m) => `Уверенность ниже порога проверки ${m[1]}.`],
  [/^Provider or parsing failure; empty prediction counted in metrics\.$/,
    () => 'Ошибка провайдера или разбора ответа; в метриках учтён пустой результат.'],
];

export function trWarning(text: string, language: Language) {
  if (language !== 'ru') return text;
  for (const [pattern, render] of warningPatterns) {
    const match = text.match(pattern);
    if (match) return render(match);
  }
  return text;
}

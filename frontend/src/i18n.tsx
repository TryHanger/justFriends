import { createContext, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

type Language = 'ru' | 'en';
const LanguageContext = createContext<{ language: Language; setLanguage: (value: Language) => void }>({
  language: 'ru', setLanguage: () => undefined,
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() =>
    localStorage.getItem('metaphor-ui-language') === 'en' ? 'en' : 'ru'
  );
  const value = useMemo(() => ({
    language,
    setLanguage: (next: Language) => {
      localStorage.setItem('metaphor-ui-language', next);
      setLanguage(next);
    },
  }), [language]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

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
  'Could not load analysis history. Check that the backend is running at http://localhost:8000.': 'Не удалось загрузить историю. Проверьте, запущен ли сервер: http://localhost:8000.',
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
  'Found Metaphors': 'Найденные метафоры', 'No metaphors detected in this document.': 'В документе метафоры не обнаружены.',
};

export function tr(text: string, language: Language) { return language === 'ru' ? (ru[text] ?? text) : text; }

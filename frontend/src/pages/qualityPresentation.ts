const testAreas: Record<string, string> = {
  test_nlp_api: 'Проверка поведения API и сохранения результатов',
  test_nlp_contracts: 'Проверка контрактов анализа текста и разметки',
  test_nlp_models: 'Проверка моделей и алгоритмов анализа',
  test_document_loader: 'Проверка извлечения текста из документов',
  test_upload_validation: 'Проверка ограничений и ошибок загрузки',
  test_standards: 'Проверка каталога стандартов и отчётов',
  test_quality_checks: 'Проверка запуска, хранения и сравнения результатов',
};
const specificPurposes: Record<string, string> = {
  test_api_persist_retrieve_and_errors: 'Сохраняет и загружает результат API; проверяет ответы при ошибках',
  test_oversized_extracted_upload_creates_no_records_or_model_call: 'Отклоняет слишком большой текст без записи и вызова модели',
  test_upload_at_extracted_limit_is_accepted: 'Принимает документ на допустимой границе размера',
  test_upload_rejects_invalid_language_before_persistence: 'Отклоняет неверный язык до сохранения данных',
  test_quality_runner_counts_junit_cases_without_guesses: 'Считает результаты из отчёта тестов без догадок',
  test_quality_runner_rejects_missing_junit: 'Не выдаёт успех при отсутствии отчёта тестов',
  test_product_measurements_compare_two_real_runs: 'Сравнивает измерения двух сохранённых запусков',
  test_api_requires_local_page_and_known_check: 'Ограничивает запуск локальным сайтом и известными проверками',
  test_invalid_span: 'Отклоняет некорректные границы фрагмента текста',
  test_exact_unicode_and_crlf_offsets: 'Сохраняет точные позиции Unicode и переводов строк',
  test_language_and_overlap: 'Проверяет язык и пересекающиеся фрагменты',
  test_docx_extracts_paragraphs_and_nested_tables_in_document_order: 'Извлекает абзацы и таблицы DOCX в исходном порядке',
};

export function testPurpose(name: string): string {
  const identifier = name.split('::').at(-1)?.split('[')[0] ?? '';
  if (specificPurposes[identifier]) return specificPurposes[identifier];
  const area = Object.entries(testAreas).find(([key]) => name.includes(key));
  return area?.[1] ?? 'Проверка отдельного сценария проекта';
}

const characteristicNames: Record<string, string> = {
  'Functional suitability': 'Функциональная пригодность',
  Reliability: 'Надёжность',
  'Performance efficiency': 'Производительность',
  Compatibility: 'Совместимость',
  'Interaction capability': 'Способность к взаимодействию',
  Security: 'Информационная безопасность',
  Maintainability: 'Сопровождаемость',
  Flexibility: 'Гибкость',
  Safety: 'Безопасность эксплуатации',
};

export const characteristicName = (name: string, en: boolean) => en ? name : characteristicNames[name] ?? name;


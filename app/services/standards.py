"""Project-specific teaching examples inspired by the lab assignments.

These are evidence mappings, not claims of certification or ISO conformance.
"""

from pathlib import Path

from app.schemas.standards import (
    LifecycleProcess,
    LifecycleState,
    SoaArchitecture,
    SoaLayer,
    StandardInfo,
)

ROOT = Path(__file__).resolve().parents[2]


def _standard(designation, organization, title, domain, purpose, example, url, evidence):
    return StandardInfo(
        designation=designation, organization=organization, title=title,
        domain=domain, purpose=purpose, example_use=example,
        source_url=url, project_evidence=evidence,
    )


STANDARDS = [
    _standard("ISO/IEC 27034-1:2011", "ISO/IEC", "Application security — Overview and concepts", "Безопасность", "Руководство по встраиванию безопасности в процессы управления приложением.", "Связать требование, анализ опасных конструкций, исправление и повторную проверку.", "https://www.iso.org/standard/44378.html", ["app/services/security_lab.py", "tests/test_security_lab.py"]),
    _standard("OWASP Top 10:2025", "OWASP", "Web application security risks", "Безопасность", "Обзор ключевых рисков веб-приложений; A05:2025 включает инъекции.", "Классифицировать потенциально опасные SQL, eval и shell-конструкции с учётом условий эксплуатации.", "https://top10.owasp.org/2025/0x00_2025-Introduction/", ["app/services/security_lab.py", "frontend/src/pages/SecurityLab.tsx"]),
    _standard("ISO/IEC/IEEE 12207:2017", "ISO/IEC/IEEE", "Software life cycle processes", "Жизненный цикл", "Рамка процессов разработки и сопровождения ПО.", "Связать требования, реализацию, проверку и эксплуатацию API.", "https://www.iso.org/standard/63712.html", ["ARCHITECTURE.md", "app/api/v1/router.py"]),
    _standard("ISO/IEC 25010:2023", "ISO/IEC", "Product quality model", "Качество", "Девять характеристик качества продукта; критерии и метрики определяются для проекта.", "Сопоставить функциональные тесты с функциональной пригодностью.", "https://www.iso.org/standard/78176.html", ["tests/test_nlp_api.py", "tests/test_standards.py"]),
    _standard("ISO/IEC 25023:2016", "ISO/IEC", "Measurement of system and software product quality", "Качество", "Меры качества продукта, применяемые вместе с моделью ISO/IEC 25010; пороги для проекта определяются отдельно.", "Отделить число результатов тестов от количественной оценки качества продукта.", "https://www.iso.org/standard/35747.html", ["app/services/quality_checks.py", "docs/QUALITY.md"]),
    _standard("ISO/IEC/IEEE 29148:2018", "ISO/IEC/IEEE", "Requirements engineering", "Требования", "Процессы и артефакты инженерии требований.", "Проверить соответствие контрактов API требованиям клиента.", "https://www.iso.org/standard/72089.html", ["docs/API_CONTRACT.md", "contracts/analysis-result.schema.json"]),
    _standard("ISO/IEC 27001:2022", "ISO/IEC", "Information security management systems — Requirements", "Безопасность", "Требования к системе менеджмента информационной безопасности.", "Определить риск хранения стихов и API ключей; каталог не означает сертификацию.", "https://www.iso.org/standard/27001", ["app/core/config.py"]),
    _standard("ISO/IEC/IEEE 15288:2023", "ISO/IEC/IEEE", "System life cycle processes", "Системная инженерия", "Процессы жизненного цикла системы в целом.", "Проверить готовность развертывания API, БД и UI вместе.", "https://www.iso.org/standard/81702.html", ["docker-compose.yml", "frontend/src/App.tsx"]),
    _standard("ISO/IEC/IEEE 42010:2022", "ISO/IEC/IEEE", "Architecture description", "Архитектура", "Требования к описанию архитектуры и точкам зрения.", "Описать связи фронтенда, API, модели и БД.", "https://www.iso.org/standard/74393.html", ["ARCHITECTURE.md"]),
    _standard("ISO/IEC 18384-1:2016", "ISO/IEC", "Reference Architecture for SOA — Part 1: Terminology and concepts for SOA", "Архитектура", "Словарь и принципы сервис-ориентированной архитектуры: сервис, контракт, композиция, слабая связанность.", "Описать функции проекта как сервисы с явными контрактами и потребителями.", "https://www.iso.org/standard/63104.html", ["docs/API_CONTRACT.md", "contracts/analysis-result.schema.json"]),
    _standard("ISO/IEC 18384-2:2016", "ISO/IEC", "Reference Architecture for SOA — Part 2: Reference Architecture for SOA Solutions", "Архитектура", "Эталонная архитектура SOA: пять горизонтальных слоёв от операционных систем до потребителей и четыре сквозных — интеграция, качество обслуживания, информация, управление.", "Сопоставить слои с компонентами проекта и найти пробелы: посредник интеграции, мониторинг, реестр сервисов.", "https://www.iso.org/standard/63105.html", ["ARCHITECTURE.md", "app/api/v1/router.py"]),
    _standard("ISO 31000:2018", "ISO", "Risk management — Guidelines", "Риски", "Принципы и руководство по управлению рисками.", "Вести реестр рисков ошибок анализа и утечки данных.", "https://www.iso.org/standard/65694.html", []),
    _standard("IEC 62443-4-1:2018", "IEC", "Secure product development lifecycle requirements", "Безопасность", "Процессы безопасной разработки для промышленной автоматизации; пример отдельной области IEC.", "Сравнить подход к безопасной разработке; прямое применение к этому API требует обоснования.", "https://webstore.iec.ch/en/publication/33615", []),
    _standard("IEEE 829-2008", "IEEE", "Standard for Software and System Test Documentation", "Тестирование", "Исторический стандарт документации тестирования; заменён семейством ISO/IEC/IEEE 29119.", "Сопоставить структуру отчёта об испытаниях; не использовать как актуальное требование.", "https://standards.ieee.org/standard/829-2008.html", ["tests/test_nlp_api.py"]),
    _standard("ISO/IEC/IEEE 29119-3:2021", "ISO/IEC/IEEE", "Software testing — Test documentation", "Тестирование", "Шаблоны документации тестирования для разных моделей жизненного цикла.", "Сохранить дату, статус, случаи и диагностические сообщения каждого запуска.", "https://www.iso.org/standard/79429.html", ["app/db/models.py", "tests/test_quality_checks.py"]),
    _standard("ГОСТ 34.601-90", "Национальный", "Автоматизированные системы. Стадии создания", "Системная инженерия", "Национальная модель стадий создания автоматизированной системы.", "Сравнить стадии с процессной моделью 12207; применимость зависит от контекста проекта.", "https://protect.gost.ru/document1.aspx?control=31&id=137554", []),
]


PROCESS_DEFS = [
    ("requirements", "Требования", "аналитик", [], ["docs/API_CONTRACT.md"], ["Контракт API"], []),
    ("architecture", "Архитектура", "архитектор", ["requirements"], ["ARCHITECTURE.md"], ["Описание архитектуры"], []),
    ("implementation", "Реализация", "разработчик", ["architecture"], ["app/api/v1/router.py", "app/nlp/pipeline.py", "frontend/src/App.tsx"], ["API и интерфейс"], []),
    ("integration", "Интеграция", "разработчик", ["implementation"], ["frontend/src/api.ts", "app/api/v1/router.py"], ["Связь UI и API"], []),
    ("verification", "Верификация", "инженер по тестированию", ["implementation"], ["tests/test_nlp_api.py", "tests/test_standards.py"], ["Автоматические проверки"], ["Результат последнего запуска тестов хранится только в отчёте запуска"]),
    ("validation", "Валидация", "представитель пользователей", ["integration", "verification"], [], ["Сценарии и отзыв пользователя"], ["Нет зафиксированных пользовательских испытаний"]),
    ("deployment", "Подготовка к эксплуатации", "DevOps", ["integration", "verification"], ["Dockerfile", "docker-compose.yml"], ["Конфигурация запуска"], ["Нет подтверждённого пробного развертывания"]),
    ("operation", "Эксплуатация", "оператор", ["validation", "deployment"], [], ["Журнал эксплуатации"], ["Нет свидетельств реальной эксплуатации"]),
    ("maintenance", "Сопровождение", "разработчик", ["operation"], [], ["План сопровождения"], ["Нет плана сопровождения и записей об изменениях"]),
]


def lifecycle_state(root: Path = ROOT) -> LifecycleState:
    from app.services.quality import quality_snapshot

    run_status, checked_at, run_error = quality_snapshot()
    processes = []
    outputs_by_id = {definition[0]: definition[5] for definition in PROCESS_DEFS}
    for ident, name, owner, deps, artifacts, outputs, fixed_gaps in PROCESS_DEFS:
        existing = [path for path in artifacts if (root / path).is_file()]
        missing = [f"Отсутствует {path}" for path in artifacts if path not in existing]
        gaps = missing + fixed_gaps
        if ident == "verification":
            if run_status in {None, "running"}:
                gaps = missing + ["Автоматические тесты ещё не завершены"]
            elif run_status != "PASS":
                gaps = missing + [f"Последняя проверка: {run_status}. {run_error or ''}".strip()]
            else:
                gaps = missing
        status = "missing" if not existing else "partial" if gaps else "evidenced"
        processes.append(LifecycleProcess(
            id=ident, name=name, responsible=owner,
            inputs=[item for dependency in deps for item in outputs_by_id[dependency]],
            outputs=outputs, dependencies=deps, status=status,
            evidence=existing, gaps=gaps,
        ))
    issues = [gap for process in processes for gap in process.gaps]
    critical = {"validation", "operation"}
    if any(p.id in critical and p.status != "evidenced" for p in processes):
        readiness = "not_ready"
    elif issues:
        readiness = "conditional"
    else:
        readiness = "ready"
    return LifecycleState(processes=processes, readiness=readiness, issues=issues,
                          last_checked_at=checked_at)


# ISO/IEC 18384-2 layers: id, name, name in the standard, kind, role in this project,
# artifacts that evidence it, gaps that files cannot close.
SOA_LAYER_DEFS = [
    ("operational", "Операционные системы", "Operational Systems Layer", "horizontal",
     "Среда выполнения: контейнеры API, интерфейса и PostgreSQL, файлы моделей.",
     ["docker-compose.yml", "Dockerfile", "app/db/session.py"], []),
    ("service_components", "Компоненты сервисов", "Service Component Layer", "horizontal",
     "Реализация сервисов: анализатор, конвейер NLP, проверки качества.",
     ["app/services/analyzer.py", "app/nlp/pipeline.py", "app/services/quality_checks.py"], []),
    ("services", "Сервисы", "Services Layer", "horizontal",
     "Описанные REST-сервисы: анализ, библиотека, стандарты; контракты в OpenAPI и JSON Schema.",
     ["app/api/v1/routes/analyses.py", "app/api/v1/routes/library.py",
      "contracts/analysis-result.schema.json", "docs/API_CONTRACT.md"], []),
    ("business_process", "Бизнес-процессы", "Business Process Layer", "horizontal",
     "Композиция сервисов в процесс анализа: очередь задач и этапы A–E конвейера.",
     ["app/services/analysis_jobs.py", "app/nlp/pipeline.py"],
     ["Композиция задана только в коде: нет описания процесса анализа как модели (например, BPMN)"]),
    ("consumer", "Потребители", "Consumer Layer", "horizontal",
     "Веб-интерфейс React и его клиент API.",
     ["frontend/src/App.tsx", "frontend/src/api.ts"], []),
    ("integration", "Интеграция", "Integration Layer", "cross_cutting",
     "Связь потребителей с сервисами: единый маршрутизатор /api/v1 и политика CORS.",
     ["app/api/v1/router.py", "app/main.py"],
     ["Нет посредника (шины сервисов или API-шлюза): интерфейс вызывает сервисы напрямую по REST"]),
    ("quality_of_service", "Качество обслуживания", "Quality of Service Layer", "cross_cutting",
     "Надёжность и безопасность: проверка здоровья, тесты качества, лаборатория безопасности.",
     ["app/api/v1/routes/health.py", "app/services/quality.py", "app/services/security_lab.py"],
     ["Нет мониторинга в эксплуатации: доступность и время ответа сервисов не измеряются"]),
    ("information", "Информация", "Information Layer", "cross_cutting",
     "Модели данных и схемы обмена: Pydantic, ORM, таксономия фигур.",
     ["app/schemas/analysis.py", "app/db/models.py", "contracts/taxonomy.json"], []),
    ("governance", "Управление", "Governance Layer", "cross_cutting",
     "Контроль изменений сервисов: версия API в пути, CI, описание архитектуры.",
     [".github/workflows/quality.yml", "ARCHITECTURE.md", "docs/QUALITY.md"],
     ["Нет реестра сервисов и правил версионирования: не определено, когда вводить /api/v2"]),
]


def soa_architecture(root: Path = ROOT) -> SoaArchitecture:
    """Evidence for each ISO/IEC 18384-2 layer; a mapping, not a conformance claim."""
    layers = []
    for ident, name, standard_name, kind, role, artifacts, fixed_gaps in SOA_LAYER_DEFS:
        existing = [path for path in artifacts if (root / path).is_file()]
        gaps = [f"Отсутствует {path}" for path in artifacts if path not in existing] + fixed_gaps
        status = "missing" if not existing else "partial" if gaps else "evidenced"
        layers.append(SoaLayer(
            id=ident, name=name, standard_name=standard_name, kind=kind, role=role,
            status=status, evidence=existing, gaps=gaps,
        ))
    issues = [gap for layer in layers for gap in layer.gaps]
    # Without any of the five horizontal layers there is no SOA solution to speak of.
    if any(layer.kind == "horizontal" and layer.status == "missing" for layer in layers):
        alignment = "not_aligned"
    elif issues:
        alignment = "partial"
    else:
        alignment = "aligned"
    return SoaArchitecture(layers=layers, alignment=alignment, issues=issues)


def search_standards(query: str, domain: str | None = None) -> list[StandardInfo]:
    needle = query.casefold().strip()
    return [s for s in STANDARDS if
            (not needle or any(needle in value.casefold() for value in
             (s.designation, s.domain, s.purpose))) and
            (not domain or s.domain.casefold() == domain.casefold())]

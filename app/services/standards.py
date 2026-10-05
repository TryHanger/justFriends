"""Project-specific teaching examples inspired by the lab assignments.

These are evidence mappings, not claims of certification or ISO conformance.
"""

from pathlib import Path

from app.schemas.standards import LifecycleProcess, LifecycleState, StandardInfo

ROOT = Path(__file__).resolve().parents[2]


def _standard(designation, organization, title, domain, purpose, example, url, evidence):
    return StandardInfo(
        designation=designation, organization=organization, title=title,
        domain=domain, purpose=purpose, example_use=example,
        source_url=url, project_evidence=evidence,
    )


STANDARDS = [
    _standard("ISO/IEC/IEEE 12207:2017", "ISO/IEC/IEEE", "Software life cycle processes", "Жизненный цикл", "Рамка процессов разработки и сопровождения ПО.", "Связать требования, реализацию, проверку и эксплуатацию API.", "https://www.iso.org/standard/63712.html", ["ARCHITECTURE.md", "app/api/v1/router.py"]),
    _standard("ISO/IEC 25010:2023", "ISO/IEC", "Product quality model", "Качество", "Девять характеристик качества продукта; критерии и метрики определяются для проекта.", "Сопоставить функциональные тесты с функциональной пригодностью.", "https://www.iso.org/standard/78176.html", ["tests/test_nlp_api.py", "tests/test_standards.py"]),
    _standard("ISO/IEC/IEEE 29148:2018", "ISO/IEC/IEEE", "Requirements engineering", "Требования", "Процессы и артефакты инженерии требований.", "Проверить соответствие контрактов API требованиям клиента.", "https://www.iso.org/standard/72089.html", ["docs/API_CONTRACT.md", "contracts/analysis-result.schema.json"]),
    _standard("ISO/IEC 27001:2022", "ISO/IEC", "Information security management systems — Requirements", "Безопасность", "Требования к системе менеджмента информационной безопасности.", "Определить риск хранения стихов и API ключей; каталог не означает сертификацию.", "https://www.iso.org/standard/27001", ["app/core/config.py"]),
    _standard("ISO/IEC/IEEE 15288:2023", "ISO/IEC/IEEE", "System life cycle processes", "Системная инженерия", "Процессы жизненного цикла системы в целом.", "Проверить готовность развертывания API, БД и UI вместе.", "https://www.iso.org/standard/81702.html", ["docker-compose.yml", "frontend/src/App.tsx"]),
    _standard("ISO/IEC/IEEE 42010:2022", "ISO/IEC/IEEE", "Architecture description", "Архитектура", "Требования к описанию архитектуры и точкам зрения.", "Описать связи фронтенда, API, модели и БД.", "https://www.iso.org/standard/74393.html", ["ARCHITECTURE.md"]),
    _standard("ISO 31000:2018", "ISO", "Risk management — Guidelines", "Риски", "Принципы и руководство по управлению рисками.", "Вести реестр рисков ошибок анализа и утечки данных.", "https://www.iso.org/standard/65694.html", []),
    _standard("IEC 62443-4-1:2018", "IEC", "Secure product development lifecycle requirements", "Безопасность", "Процессы безопасной разработки для промышленной автоматизации; пример отдельной области IEC.", "Сравнить подход к безопасной разработке; прямое применение к этому API требует обоснования.", "https://webstore.iec.ch/en/publication/33615", []),
    _standard("IEEE 829-2008", "IEEE", "Standard for Software and System Test Documentation", "Тестирование", "Исторический стандарт документации тестирования; заменён семейством ISO/IEC/IEEE 29119.", "Сопоставить структуру отчёта об испытаниях; не использовать как актуальное требование.", "https://standards.ieee.org/standard/829-2008.html", ["tests/test_nlp_api.py"]),
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


def search_standards(query: str, domain: str | None = None) -> list[StandardInfo]:
    needle = query.casefold().strip()
    return [s for s in STANDARDS if
            (not needle or any(needle in value.casefold() for value in
             (s.designation, s.domain, s.purpose))) and
            (not domain or s.domain.casefold() == domain.casefold())]

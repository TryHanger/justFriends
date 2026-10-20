# Project quality policy

This project uses executable checks and inspectable artifacts. ISO references guide the project checklist; they are not certificates or a claim that every clause is implemented.

## Reproducible checks

| Check | Command | Meaning of success |
| --- | --- | --- |
| Python rules | `python -m ruff check app tests scripts` | Selected syntax, import, unused-code, modernization and bug-risk rules passed |
| Backend and contracts | `python -X utf8 -m pytest -q -rs` | Collected tests passed; the summary separately reports skips |
| Frontend rules | `npm --prefix frontend run lint` | Oxlint reports no warnings or errors |
| Frontend behavior | `npm --prefix frontend test` | Component and transport regression tests passed |
| Types and build | `npm --prefix frontend run build` | TypeScript checks and Vite production build passed |

Install Python `.[dev,quality]` and use Node 24.15+ in the 24.x series with `npm ci` in `frontend`. Ruff rules are explicitly declared in `pyproject.toml`; FastAPI parameter declarations are recognized as immutable metadata rather than suppressed globally. The npm lockfile is committed. Python dependencies currently use bounded version ranges, so their resolution is not fully locked.

`.github/workflows/quality.yml` runs these checks for pushes and pull requests, tests Python 3.11 and 3.12, and uploads the pytest JUnit report. No API keys or paid model calls are needed. A skipped optional neural-model test is visible in pytest and its report; this CI suite does not validate trained model quality. Branch protection must require the workflow checks in repository settings if failed checks should block merges. Merely committing the workflow does not enable branch protection or prove a successful remote run.

## What the Standards page measures

- The reference tab is an informational catalog.
- The lifecycle tab inspects named local project files. `evidenced` means that an artifact is available, not that its contents were approved or that the process is complete. Missing artifacts remain missing.
- The lifecycle view includes the last quality-run status and timestamp from the current API process. Before a run it is unknown; a failed or unavailable rerun clears an earlier passing status. The snapshot is lost on restart and is not shared across API workers.
- The quality dashboard starts a persisted backend test run and shows its progress, cases, skipped reasons and source record. A run with successful executed tests and only optional skips is presented as tests passed with skips shown separately. Missing results, failures and timeouts remain distinct states.
- The separate «Проверки проекта» tab persists five kinds of tool runs, reports availability, and compares same-kind runs. See [the checks center guide](CHECKS_CENTER.md). Static findings are never counted as unit tests.
- The «Качество и тесты» tab automatically loads ISO/IEC 25023:2016 project indicators from saved backend, frontend, Ruff and TypeScript runs. Test pass share excludes skips from the denominator and shows them separately; 100% is a test pass share, never overall product quality. Each card compares the latest two runs of the same tool and links to both source records. A missing or unusable run is unmeasured, never zero. The nine ISO/IEC 25010:2023 characteristics show partial evidence or no assessment, not conformance. These formulas are not claimed to be verbatim ISO measures, and no universal quality threshold is assigned.
- The local checks center runs frontend tests, TypeScript, and the Vite build in an isolated Node.js container when Docker Compose starts `frontend-checks`. It does not fetch CI results. Human approval, deployment readiness, security, performance and research validity remain unassessed by these checks.

## Mapping to standards

These are project-defined evidence links, not automatic clause-by-clause conformance tests. The public publisher pages establish the scope of the referenced standards; this policy does not substitute for their full text.

| Reference | Project evidence | What still needs human assessment |
| --- | --- | --- |
| [ISO/IEC/IEEE 29148:2018 — Requirements engineering](https://www.iso.org/standard/72089.html) | `docs/API_CONTRACT.md`, `docs/NLP_CONTRACT.md`, schema and HTTP regression tests | Stakeholder approval, completeness and traceability of requirements |
| [ISO/IEC/IEEE 12207:2017 — Software life cycle processes](https://www.iso.org/standard/63712.html) | `ARCHITECTURE.md`, implementation, tests and workflow configuration | Process tailoring, review decisions, operational and maintenance evidence; this is the selected edition in the catalog |
| [ISO/IEC 25010:2023 — Product quality model](https://www.iso.org/standard/78176.html) | API/component tests, static checks and production build | Performance, security, usability and other quality characteristics require specific criteria and measurements |
| [ISO/IEC 25023:2016 — Measurement of system and software product quality](https://www.iso.org/standard/35747.html) | Project-defined indicators calculated from saved check results, with formulas, dates and source runs | The complete set of standard measures and project acceptance thresholds have not been adopted; editions of 25023 and 25010 require explicit mapping |

Other standards in the reference catalog have no implemented conformance assessment. They must not be reported as satisfied merely because they are listed.

## Repository hygiene

Keep code, tests, documentation, example configurations and the npm lockfile in Git. `.gitignore` excludes real `.env` files, virtual environments, dependencies, caches, local databases and their journals, logs, generated reports, models, working datasets and agent work directories. `.env.example` files remain versionable. `.dockerignore` also excludes local credentials and heavyweight working artifacts.

Ignore rules do not remove previously tracked files or erase history. Check `git status --short` and `git diff --check` before committing. Do not publish actual API keys or machine-specific runtime files.

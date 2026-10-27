"""Small educational AST review. Submitted source is parsed, never executed."""

import ast
from collections import Counter

from pydantic import BaseModel, Field


class SecurityReviewRequest(BaseModel):
    before: str = Field(max_length=12000)
    after: str = Field(max_length=12000)
    likelihood: int = Field(default=3, ge=1, le=3)
    impact: int = Field(default=3, ge=1, le=3)


class SecurityFinding(BaseModel):
    rule: str
    line: int
    title: str
    category: str = "A05:2025 Injection"
    consequence: str
    recommendation: str


class CodeReview(BaseModel):
    findings: list[SecurityFinding]
    syntax_error: str | None = None


class SecurityReview(BaseModel):
    before: CodeReview
    after: CodeReview
    removed: int
    remaining: int
    introduced: int
    risk_score: int
    risk_level: str


RULES = {
    "eval": (
        "Вычисление выражения через eval",
        "Если выражение приходит извне, возможно выполнение чужого Python-кода.",
        "Для данных используйте json.loads; для вычислений — явный список операций.",
    ),
    "sql": (
        "Динамический текст SQL-запроса",
        "Если в строку попадает ввод пользователя, возможно чтение или изменение чужих данных.",
        "Передавайте данные отдельно от запроса: execute('SELECT … WHERE name = ?', (name,)).",
    ),
    "shell": (
        "Запуск команды через shell=True",
        "Если ввод влияет на команду, оболочка может выполнить дополнительные команды.",
        "Используйте список аргументов, shell=False и проверку допустимых значений.",
    ),
}


def inspect_source(source: str) -> CodeReview:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return CodeReview(findings=[], syntax_error="Код не разобран. Проверьте синтаксис Python.")

    aliases: dict[str, str] = {}
    # Resolve conventional imports only; this is deliberately not a data-flow engine.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"

    def name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return f"{name(node.value)}.{node.attr}"
        return ""

    def dynamic(node: ast.AST) -> bool:
        return (isinstance(node, ast.JoinedStr) or
                isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)) or
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "format")

    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = name(node.func)
        rule = None
        if target in {"eval", "builtins.eval"}:
            rule = "eval"
        elif isinstance(node.func, ast.Attribute) and node.func.attr in {"execute", "executemany"}:
            if node.args and dynamic(node.args[0]):
                rule = "sql"
        elif target in {"subprocess.run", "subprocess.call", "subprocess.Popen",
                        "subprocess.check_call", "subprocess.check_output"}:
            if any(k.arg == "shell" and isinstance(k.value, ast.Constant)
                   and k.value.value is True for k in node.keywords):
                rule = "shell"
        if rule:
            title, consequence, recommendation = RULES[rule]
            findings.append(SecurityFinding(rule=rule, line=node.lineno, title=title,
                                            consequence=consequence, recommendation=recommendation))
    return CodeReview(findings=sorted(findings, key=lambda finding: finding.line))


def review_code(request: SecurityReviewRequest) -> SecurityReview:
    before, after = inspect_source(request.before), inspect_source(request.after)
    old = Counter(item.rule for item in before.findings)
    new = Counter(item.rule for item in after.findings)
    comparable = before.syntax_error is None and after.syntax_error is None
    score = request.likelihood * request.impact
    return SecurityReview(
        before=before, after=after,
        removed=sum((old - new).values()) if comparable else 0,
        remaining=sum((old & new).values()) if comparable else 0,
        introduced=sum((new - old).values()) if comparable else 0,
        risk_score=score, risk_level="высокий" if score >= 6 else "средний" if score >= 3 else "низкий",
    )

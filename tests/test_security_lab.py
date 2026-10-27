"""Security review behaviour on owned educational snippets only."""

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes.standards import router
from app.services.security_lab import SecurityReviewRequest, inspect_source, review_code


@pytest.mark.parametrize("source,rules", [
    ('eval(user_text)', ['eval']),
    ('db.execute("SELECT * FROM users WHERE name=" + name)', ['sql']),
    ('import subprocess as sp\nsp.run(command, shell=True)', ['shell']),
    ('from subprocess import run as launch\nlaunch(command, shell=True)', ['shell']),
    ('db.execute("SELECT * FROM users WHERE name = ?", (name,))', []),
    ('import subprocess\nsubprocess.run(["ls", "--", path], shell=False)', []),
    ('import json\njson.loads(user_text)', []),
    ('db.execute(f"SELECT {column} FROM users")', ['sql']),
    ('db.execute("SELECT {} FROM users".format(column))', ['sql']),
    ('# eval(user_text)\ntext = "subprocess.run(command, shell=True)"', []),
])
def test_reports_syntax_patterns_without_running_code(source, rules):
    assert [finding.rule for finding in inspect_source(source).findings] == rules


def test_submitted_code_is_not_executed(tmp_path):
    target = tmp_path / "must-not-exist"
    inspect_source(f"from pathlib import Path\nPath({str(target)!r}).touch()\neval('1')")
    assert not target.exists()


def test_comparison_ignores_line_shifts_and_keeps_counts():
    result = review_code(SecurityReviewRequest(
        before='eval(a)\neval(b)', after='\n\n\neval(a)\nimport subprocess\nsubprocess.run(cmd, shell=True)',
        likelihood=2, impact=3,
    ))
    assert (result.removed, result.remaining, result.introduced) == (1, 1, 1)
    assert result.after.findings[0].line == 4
    assert (result.risk_score, result.risk_level) == (6, "высокий")


def test_invalid_after_is_not_reported_as_fixed():
    result = review_code(SecurityReviewRequest(before="eval(a)", after="def broken("))
    assert result.after.syntax_error
    assert result.removed == 0


def test_api_validates_size_and_risk_scale():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.post('/security/review', json={'before': 'eval(a)', 'after': 'value = 1'})
        assert response.status_code == 200
        assert response.json()['removed'] == 1
        assert client.post('/security/review', json={
            'before': 'a' * 12001, 'after': '',
        }).status_code == 422
        assert client.post('/security/review', json={
            'before': '', 'after': '', 'impact': 4,
        }).status_code == 422


def test_parameterized_sql_example_treats_input_as_data():
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE users (name TEXT)')
        db.executemany('INSERT INTO users VALUES (?)', [('Alice',), ("O'Neil",)])
        for value, expected in [('Alice', [('Alice',)]), ("O'Neil", [("O'Neil",)]),
                                ("' OR 1=1 --", []), ('unknown', [])]:
            assert db.execute('SELECT * FROM users WHERE name = ?', (value,)).fetchall() == expected
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 2

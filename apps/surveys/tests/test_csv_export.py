"""CSV export safety and content tests."""

import csv
import io

import pytest
from apps.surveys.repositories import ResponseRepository
from apps.surveys.views import _csv_safe
from django.urls import reverse


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, ""),
        ("hello", "hello"),
        ("=1+1", "'=1+1"),
        ("+1234", "'+1234"),
        ("-10", "'-10"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\tcmd", "'\tcmd"),
        ("\rcmd", "'\rcmd"),
        ("=cmd|'/c calc'!A1", "'=cmd|'/c calc'!A1"),
    ],
)
def test_csv_safe_prefixes_formula_triggers(raw, expected):
    assert _csv_safe(raw) == expected


@pytest.mark.django_db
def test_export_csv_sanitizes_respondent_formula_answers(staff_user, client, full_survey):
    survey = full_survey["survey"]
    payload = "=cmd|'/c calc'!A1"
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, full_survey["short"], {"value": payload})
    ResponseRepository.complete(response)

    client.force_login(staff_user)
    result = client.get(reverse("surveys:export_csv", args=[survey.id]))
    assert result.status_code == 200

    rows = list(csv.reader(io.StringIO(result.content.decode())))
    assert len(rows) >= 2
    answer_cell = rows[1][rows[0].index("Name")]
    assert answer_cell == f"'{payload}"
    assert answer_cell.startswith("'=")

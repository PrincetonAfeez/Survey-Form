""" Tests for surveys app display functions """

from datetime import date
from decimal import Decimal

import pytest
from apps.surveys.display import format_answer_value, trim_decimal
from apps.surveys.models import Answer, Question, Response
from apps.surveys.repositories import ResponseRepository


def test_trim_decimal_formats_values():
    assert trim_decimal(Decimal("3.50")) == "3.5"
    assert trim_decimal(None) == "N/A"
    assert trim_decimal("plain") == "plain"


def test_format_answer_value_handles_none():
    assert format_answer_value(None) == ""


@pytest.mark.django_db
def test_format_answer_value_all_types(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    payloads = [
        (full_survey["short"], {"value": "hello"}),
        (full_survey["number"], {"value": Decimal("3.5")}),
        (full_survey["date"], {"value": date(2026, 5, 16)}),
        (full_survey["single"], {"value": full_survey["single_yes"]}),
        (full_survey["multi"], {"value": [full_survey["multi_a"]]}),
        (full_survey["rating"], {"value": full_survey["rating"].choices.get(label="2")}),
        (full_survey["likert"], {"value": full_survey["likert"].choices.get(label="Neutral")}),
    ]
    for question, payload in payloads:
        answer = ResponseRepository.save_answer(response, question, payload)
        assert format_answer_value(answer)

    assert format_answer_value(None) == ""


@pytest.mark.django_db
def test_format_answer_value_empty_optional_fields(full_survey):
    survey = full_survey["survey"]
    q = Question.objects.create(survey=survey, order=99, text="N", type=Question.Type.NUMBER)
    response = Response.objects.create(survey=survey)
    answer = Answer.objects.create(response=response, question=q)
    assert format_answer_value(answer) == ""

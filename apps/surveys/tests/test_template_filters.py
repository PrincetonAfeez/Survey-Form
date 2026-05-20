"""Tests for surveys app template filters"""

from datetime import date

import pytest
from apps.surveys.models import Choice, Question, Response, Survey
from apps.surveys.repositories import ResponseRepository
from apps.surveys.templatetags.survey_extras import answer_display, duration, trim_decimal


@pytest.mark.django_db
def test_template_filters_cover_answer_types():
    survey = Survey.objects.create(title="Filters", slug="filters")
    response = Response.objects.create(survey=survey)
    text_q = Question.objects.create(
        survey=survey, order=1, text="Text", type=Question.Type.SHORT_TEXT
    )
    number_q = Question.objects.create(
        survey=survey, order=2, text="Number", type=Question.Type.NUMBER
    )
    date_q = Question.objects.create(survey=survey, order=3, text="Date", type=Question.Type.DATE)
    single_q = Question.objects.create(
        survey=survey, order=4, text="Single", type=Question.Type.SINGLE_CHOICE
    )
    single = Choice.objects.create(question=single_q, order=1, label="One")
    multi_q = Question.objects.create(
        survey=survey, order=5, text="Multi", type=Question.Type.MULTIPLE_CHOICE
    )
    multi = Choice.objects.create(question=multi_q, order=1, label="Many")
    rating_q = Question.objects.create(
        survey=survey, order=6, text="Rating", type=Question.Type.RATING
    )
    likert_q = Question.objects.create(
        survey=survey, order=7, text="Likert", type=Question.Type.LIKERT
    )

    answers = [
        ResponseRepository.save_answer(response, text_q, {"value": "hello"}),
        ResponseRepository.save_answer(response, number_q, {"value": "3.50"}),
        ResponseRepository.save_answer(response, date_q, {"value": date(2026, 5, 16)}),
        ResponseRepository.save_answer(response, single_q, {"value": single}),
        ResponseRepository.save_answer(response, multi_q, {"value": [multi]}),
        ResponseRepository.save_answer(
            response, rating_q, {"value": rating_q.choices.get(label="2")}
        ),
        ResponseRepository.save_answer(
            response, likert_q, {"value": likert_q.choices.get(label="Neutral")}
        ),
    ]

    rendered = [answer_display(answer) for answer in answers]

    assert rendered == ["hello", "3.5", "2026-05-16", "One", "Many", "2", "Neutral"]
    assert answer_display(None) == ""
    assert trim_decimal(None) == "N/A"
    assert trim_decimal("3.5") == "3.5"
    assert duration(None) == "N/A"
    assert duration(59) == "59s"
    assert duration(65) == "1m 5s"
    assert duration(3660) == "1h 1m"
    assert duration("not-a-number") == "N/A"
    assert duration(-10) == "N/A"

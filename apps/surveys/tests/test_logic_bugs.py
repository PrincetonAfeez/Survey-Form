"""Regression tests for smaller logic bugs C.7–C.10."""

from decimal import Decimal

import pytest
from apps.surveys.admin import ChoiceInline, QuestionAdmin
from apps.surveys.aggregators import response_metrics
from apps.surveys.forms import _initial_for, form_for_question
from apps.surveys.models import Choice, Question, Response, Survey
from apps.surveys.repositories import ResponseRepository, rating_value
from django.contrib.admin.sites import AdminSite
from django.template import Context, Template
from django.urls import reverse


@pytest.mark.django_db
def test_raw_table_pagination_urlencodes_query():
    template = Template('<a href="?page=2&amp;q={{ q|urlencode }}">next</a>')
    rendered = template.render(Context({"q": "a&b+c"}))
    assert "a%26b%2Bc" in rendered


@pytest.mark.django_db
def test_response_metrics_includes_zero_second_completions(branching_survey):
    survey, *_ = branching_survey
    survey.responses.all().delete()
    fast = ResponseRepository.start(survey)
    fast.completed_at = fast.started_at
    fast.save(update_fields=["completed_at"])

    metrics = response_metrics(survey)

    assert metrics["median_completion_seconds"] == 0


@pytest.mark.django_db
def test_rating_initial_matches_order_fallback_not_only_label():
    survey = Survey.objects.create(title="Custom rating", slug="custom-rating")
    question = Question.objects.create(
        survey=survey, order=1, text="Rate", type=Question.Type.RATING
    )
    Choice.objects.filter(question=question).delete()
    custom = Choice.objects.create(question=question, order=3, label="Good")
    response = Response.objects.create(survey=survey)
    answer = ResponseRepository.save_answer(response, question, {"value": custom})
    assert answer.number_value == Decimal("3")

    initial = _initial_for(answer)
    assert initial == custom.id

    rebound = form_for_question(question, instance=answer)
    assert rebound.fields["value"].initial == custom.id


@pytest.mark.django_db
def test_rating_value_and_initial_stay_consistent():
    survey = Survey.objects.create(title="R", slug="r-val")
    question = Question.objects.create(
        survey=survey, order=1, text="Rate", type=Question.Type.RATING
    )
    choice = question.choices.get(label="4")
    assert rating_value(choice) == Decimal("4")

    response = Response.objects.create(survey=survey)
    answer = ResponseRepository.save_answer(response, question, {"value": choice})
    assert _initial_for(answer) == choice.id


@pytest.mark.django_db
def test_question_admin_shows_choice_inline_only_for_choice_types():
    survey = Survey.objects.create(title="S", slug="admin-inline")
    rating = Question.objects.create(
        survey=survey, order=1, text="Stars", type=Question.Type.RATING
    )
    likert = Question.objects.create(
        survey=survey, order=2, text="Agree", type=Question.Type.LIKERT
    )
    single = Question.objects.create(
        survey=survey, order=3, text="Pick", type=Question.Type.SINGLE_CHOICE
    )
    multi = Question.objects.create(
        survey=survey, order=4, text="Many", type=Question.Type.MULTIPLE_CHOICE
    )
    short = Question.objects.create(
        survey=survey, order=5, text="Name", type=Question.Type.SHORT_TEXT
    )
    number = Question.objects.create(
        survey=survey, order=6, text="Count", type=Question.Type.NUMBER
    )
    admin = QuestionAdmin(Question, AdminSite())

    assert admin.get_inlines(None, rating) == []
    assert admin.get_inlines(None, likert) == []
    assert admin.get_inlines(None, short) == []
    assert admin.get_inlines(None, number) == []
    assert admin.get_inlines(None, single) == [ChoiceInline]
    assert admin.get_inlines(None, multi) == [ChoiceInline]


@pytest.mark.django_db
def test_results_raw_pagination_preserves_special_query(client, branching_survey, staff_user):
    survey, _q1, q2, *_ = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q2, {"value": Decimal("42")})
    text_q = Question.objects.create(
        survey=survey,
        order=99,
        text="Notes",
        type=Question.Type.SHORT_TEXT,
        is_required=False,
    )
    for index in range(26):
        row = ResponseRepository.start(survey)
        ResponseRepository.save_answer(row, text_q, {"value": f"a&b-{index}"})
    client.force_login(staff_user)

    page = client.get(
        reverse("surveys:results_raw", args=[survey.id]),
        {"q": "a&b", "page": 1},
    )
    assert page.status_code == 200
    assert b"page=2" in page.content
    assert b"a%26b" in page.content

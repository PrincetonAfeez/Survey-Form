"""Tests for surveys app aggregators."""

from datetime import date
from decimal import Decimal

import pytest
from apps.surveys.aggregators import (
    aggregate_choice,
    aggregate_date,
    aggregate_multiple_choice,
    aggregate_number,
    aggregate_question,
    aggregate_survey,
    aggregate_text,
    response_metrics,
)
from apps.surveys.repositories import ResponseRepository
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


@pytest.mark.django_db
def test_aggregate_survey_returns_all_questions(full_survey):
    aggregates = aggregate_survey(full_survey["survey"])
    assert len(aggregates) == full_survey["survey"].questions.count()
    kinds = {item["kind"] for item in aggregates}
    assert "choice" in kinds
    assert "number" in kinds
    assert "text" in kinds
    assert "date" in kinds


@pytest.mark.django_db
def test_aggregate_question_dispatches_by_type(full_survey):
    assert aggregate_question(full_survey["short"])["kind"] == "text"
    assert aggregate_question(full_survey["single"])["kind"] == "choice"
    assert aggregate_question(full_survey["multi"])["kind"] == "choice"
    assert aggregate_question(full_survey["number"])["kind"] == "number"
    assert aggregate_question(full_survey["rating"])["kind"] == "number"
    assert aggregate_question(full_survey["date"])["kind"] == "date"


@pytest.mark.django_db
def test_aggregate_choice_excludes_incomplete_responses(branching_survey):
    survey, q1, _q2, _q3, remote = branching_survey
    office = q1.choices.get(label="Office")
    draft = ResponseRepository.start(survey)
    ResponseRepository.save_answer(draft, q1, {"value": remote})
    complete = ResponseRepository.start(survey)
    ResponseRepository.save_answer(complete, q1, {"value": office})
    ResponseRepository.complete(complete)

    result = aggregate_choice(q1)
    assert result["total"] == 1
    assert result["rows"][0]["count"] == 0
    assert result["rows"][1]["count"] == 1


@pytest.mark.django_db
def test_aggregate_choice_and_multiple_choice(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    ResponseRepository.save_answer(
        response, full_survey["single"], {"value": full_survey["single_yes"]}
    )
    ResponseRepository.save_answer(
        response, full_survey["multi"], {"value": [full_survey["multi_a"]]}
    )
    ResponseRepository.complete(response)

    single = aggregate_choice(full_survey["single"])
    assert single["total"] == 1
    assert single["rows"][0]["count"] == 1

    multi = aggregate_multiple_choice(full_survey["multi"])
    assert multi["total"] == 1
    assert multi["rows"][0]["count"] == 1


@pytest.mark.django_db
def test_aggregate_number_empty_and_populated(full_survey):
    empty = aggregate_number(full_survey["number"])
    assert empty["count"] == 0
    assert empty["mean"] is None

    r1 = ResponseRepository.start(full_survey["survey"])
    r2 = ResponseRepository.start(full_survey["survey"])
    ResponseRepository.save_answer(r1, full_survey["number"], {"value": Decimal("10")})
    ResponseRepository.complete(r1)
    ResponseRepository.save_answer(r2, full_survey["number"], {"value": Decimal("20")})
    ResponseRepository.complete(r2)

    populated = aggregate_number(full_survey["number"])
    assert populated["count"] == 2
    assert populated["min"] == Decimal("10")
    assert populated["max"] == Decimal("20")


@pytest.mark.django_db
def test_aggregate_number_rating_includes_scale_rows(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    choice = full_survey["rating"].choices.get(label="5")
    ResponseRepository.save_answer(response, full_survey["rating"], {"value": choice})
    ResponseRepository.complete(response)

    result = aggregate_number(full_survey["rating"], rating=True)
    assert len(result["rows"]) == 5
    assert result["rows"][-1]["count"] == 1


@pytest.mark.django_db
def test_aggregate_text_count_vs_sample_limit(full_survey):
    for _ in range(30):
        r = ResponseRepository.start(full_survey["survey"])
        ResponseRepository.save_answer(r, full_survey["short"], {"value": "hello"})
        ResponseRepository.complete(r)

    result = aggregate_text(full_survey["short"])
    assert result["count"] == 30
    assert len(list(result["answers"])) <= 25


@pytest.mark.django_db
def test_aggregate_date_groups_by_week(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    ResponseRepository.save_answer(response, full_survey["date"], {"value": date(2026, 5, 16)})
    ResponseRepository.complete(response)
    result = aggregate_date(full_survey["date"])
    assert len(result["rows"]) >= 1
    assert result["rows"][0]["count"] == 1


@pytest.mark.django_db
def test_response_metrics(branching_survey):
    from datetime import timedelta

    from django.utils import timezone

    survey, q1, _q2, _q3, remote = branching_survey
    draft = ResponseRepository.start(survey)
    ResponseRepository.save_answer(draft, q1, {"value": remote})
    done = ResponseRepository.start(survey)
    done.started_at = timezone.now() - timedelta(minutes=2)
    done.save(update_fields=["started_at"])
    ResponseRepository.complete(done)

    metrics = response_metrics(survey)
    assert metrics["started"] == 2
    assert metrics["complete"] == 1
    assert metrics["completion_rate"] == 50.0
    assert metrics["median_completion_seconds"] is not None
    assert metrics["median_completion_seconds"] >= 60


@pytest.mark.django_db
def test_response_metrics_empty_survey():
    from apps.surveys.models import Survey

    survey = Survey.objects.create(title="Empty", slug="empty-metrics")
    metrics = response_metrics(survey)
    assert metrics["started"] == 0
    assert metrics["completion_rate"] == 0
    assert metrics["median_completion_seconds"] is None


@pytest.mark.django_db
def test_aggregate_question_unsupported_type_raises():
    from apps.surveys.models import Question, Survey

    survey = Survey.objects.create(title="X", slug="x-agg")
    q = Question.objects.create(survey=survey, order=1, text="?", type=Question.Type.SHORT_TEXT)
    Question.objects.filter(pk=q.pk).update(type="bogus")
    q.refresh_from_db()
    with pytest.raises(ValueError, match="Unsupported"):
        aggregate_question(q)


@pytest.mark.django_db
@settings(max_examples=12, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.lists(st.integers(min_value=1, max_value=5), min_size=1, max_size=8))
def test_rating_mean_stays_inside_scale(branching_survey, ratings):
    survey, _q1, _q2, q3, _remote = branching_survey
    survey.responses.all().delete()
    choices = {int(choice.label): choice for choice in q3.choices.all()}
    for rating in ratings:
        response = ResponseRepository.start(survey)
        ResponseRepository.save_answer(response, q3, {"value": choices[rating]})
        ResponseRepository.complete(response)

    aggregate = aggregate_number(q3, rating=True)

    assert Decimal("1") <= aggregate["mean"] <= Decimal("5")
    assert sum(row["count"] for row in aggregate["rows"]) == len(ratings)


@pytest.mark.django_db
def test_choice_counts_sum_to_answer_count(branching_survey):
    survey, q1, _q2, _q3, remote = branching_survey
    office = q1.choices.get(label="Office")
    for choice in [remote, office, office]:
        response = ResponseRepository.start(survey)
        ResponseRepository.save_answer(response, q1, {"value": choice})
        ResponseRepository.complete(response)

    aggregate = aggregate_choice(q1)

    assert sum(row["count"] for row in aggregate["rows"]) == 3

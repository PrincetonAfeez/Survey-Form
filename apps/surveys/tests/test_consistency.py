"""Consistency fixes: done page guard, number distribution bars"""

from decimal import Decimal

import pytest
from apps.surveys.aggregators import aggregate_number
from apps.surveys.repositories import ResponseRepository
from django.urls import reverse


@pytest.mark.django_db
def test_done_requires_completed_session(client, branching_survey):
    survey, *_ = branching_survey
    response = client.get(reverse("surveys:done", args=[survey.slug]))
    assert response.status_code == 302
    assert reverse("surveys:intro", args=[survey.slug]) in response["Location"]


@pytest.mark.django_db
def test_done_renders_after_completion(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    survey_response = survey.responses.get()
    ResponseRepository.save_answer(survey_response, q1, {"value": remote})
    ResponseRepository.save_answer(survey_response, q3, {"value": q3.choices.get(label="5")})
    ResponseRepository.complete(survey_response)

    response = client.get(reverse("surveys:done", args=[survey.slug]))
    assert response.status_code == 200
    assert b"Thanks" in response.content


@pytest.mark.django_db
def test_aggregate_number_includes_distribution_rows_for_plain_number(full_survey):
    r1 = ResponseRepository.start(full_survey["survey"])
    ResponseRepository.save_answer(r1, full_survey["number"], {"value": Decimal("10")})
    ResponseRepository.complete(r1)
    r2 = ResponseRepository.start(full_survey["survey"])
    ResponseRepository.save_answer(r2, full_survey["number"], {"value": Decimal("20")})
    ResponseRepository.complete(r2)

    result = aggregate_number(full_survey["number"], rating=False)
    assert len(result["rows"]) == 2
    assert result["rows"][0]["count"] + result["rows"][1]["count"] == 2


@pytest.mark.django_db
def test_progress_bar_uses_percent_aria(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    page = client.get(reverse("surveys:step", args=[survey.slug, 1]))
    assert b'aria-valuemax="100"' in page.content
    assert b'aria-valuemin="0"' in page.content
    assert b'role="progressbar"' in page.content

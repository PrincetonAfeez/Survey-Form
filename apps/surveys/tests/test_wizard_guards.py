""" Tests for surveys app wizard guards """

import pytest
from apps.surveys.repositories import ResponseRepository
from django.urls import reverse


@pytest.mark.django_db
def test_step_returns_404_for_unknown_question_order(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))

    response = client.get(reverse("surveys:step", args=[survey.slug, 99]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_step_redirects_when_response_is_complete(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    survey_response = survey.responses.get()
    ResponseRepository.save_answer(survey_response, q1, {"value": remote})
    ResponseRepository.save_answer(survey_response, q3, {"value": q3.choices.get(label="5")})
    ResponseRepository.complete(survey_response)

    response = client.get(reverse("surveys:step", args=[survey.slug, q3.order]))
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:done", args=[survey.slug]))


@pytest.mark.django_db
def test_step_post_blocked_when_complete(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    survey_response = survey.responses.get()
    ResponseRepository.save_answer(survey_response, q1, {"value": remote})
    ResponseRepository.save_answer(survey_response, q3, {"value": q3.choices.get(label="5")})
    ResponseRepository.complete(survey_response)

    response = client.post(
        reverse("surveys:step", args=[survey.slug, q3.order]),
        {"value": q3.choices.get(label="1").id},
    )
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:done", args=[survey.slug]))


@pytest.mark.django_db
def test_start_reuses_incomplete_session(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    first_uuid = survey.responses.get().uuid

    response = client.post(reverse("surveys:start", args=[survey.slug]))
    assert response.status_code == 302
    assert survey.responses.count() == 1
    assert survey.responses.get().uuid == first_uuid


@pytest.mark.django_db
def test_start_force_new_creates_fresh_response(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    first_uuid = survey.responses.get().uuid

    response = client.post(
        reverse("surveys:start", args=[survey.slug]),
        {"force_new": "1"},
    )
    assert response.status_code == 302
    assert survey.responses.count() == 1
    assert survey.responses.get().uuid != first_uuid


@pytest.mark.django_db
def test_exports_exclude_incomplete_responses(client, branching_survey, staff_user):
    survey, q1, _q2, _q3, remote = branching_survey
    client.force_login(staff_user)
    draft = ResponseRepository.start(survey)
    ResponseRepository.save_answer(draft, q1, {"value": remote})
    complete = ResponseRepository.start(survey)
    ResponseRepository.complete(complete)

    response = client.get(reverse("surveys:export_json", args=[survey.id]))
    payload = response.json()

    assert len(payload) == 1
    assert payload[0]["response"]["uuid"] == str(complete.uuid)

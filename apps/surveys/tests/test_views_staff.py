"""Tests for surveys app staff views"""

import json

import pytest
from apps.surveys.repositories import ResponseRepository
from apps.surveys.tokens import issue_resume_token
from django.urls import reverse


@pytest.mark.django_db
def test_resume_done_and_htmx_success_paths(client, branching_survey):
    survey, _q1, _q2, q3, remote = branching_survey
    rating = q3.choices.get(label="4")

    client.post(reverse("surveys:start", args=[survey.slug]))
    response = client.post(
        reverse("surveys:step", args=[survey.slug, 1]),
        {"value": remote.id},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert response["HX-Push-Url"].endswith(reverse("surveys:step", args=[survey.slug, 3]))

    survey_response = survey.responses.get()
    token = issue_resume_token(survey_response)
    response = client.get(reverse("surveys:resume", args=[survey.slug, token]))
    assert response.status_code == 302

    response = client.post(
        reverse("surveys:step", args=[survey.slug, q3.order]),
        {"value": rating.id},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 204
    assert response["HX-Redirect"].endswith(reverse("surveys:done", args=[survey.slug]))

    response = client.get(reverse("surveys:done", args=[survey.slug]))
    assert response.status_code == 200


@pytest.mark.django_db
def test_resume_invalid(client, branching_survey):
    survey, *_ = branching_survey

    response = client.get(reverse("surveys:resume", args=[survey.slug, "bad-token"]))

    assert response.status_code == 400
    assert b"invalid or expired" in response.content


@pytest.mark.django_db
def test_resume_wrong_survey_token(client, branching_survey, db):
    from apps.surveys.models import Survey

    survey, *_ = branching_survey
    from apps.surveys.models import Question

    other = Survey.objects.create(title="Other", slug="other-resume", is_published=False)
    Question.objects.create(survey=other, order=1, text="Other Q", type=Question.Type.SHORT_TEXT)
    other.is_published = True
    other.save()
    other_response = ResponseRepository.start(other)
    token = issue_resume_token(other_response)

    response = client.get(reverse("surveys:resume", args=[survey.slug, token]))
    assert response.status_code == 400


@pytest.mark.django_db
def test_resume_completed_redirects_to_done(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": remote})
    ResponseRepository.save_answer(response, q3, {"value": q3.choices.get(label="5")})
    ResponseRepository.complete(response)
    token = issue_resume_token(response)

    client_response = client.get(reverse("surveys:resume", args=[survey.slug, token]))
    assert client_response.status_code == 302
    assert client_response["Location"].endswith(reverse("surveys:done", args=[survey.slug]))


@pytest.mark.django_db
def test_preview_flow_is_staff_only(client, branching_survey, staff_user):
    survey, _q1, _q2, q3, remote = branching_survey

    response = client.get(reverse("surveys:preview", args=[survey.slug]))
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]

    client.force_login(staff_user)
    response = client.get(reverse("surveys:preview", args=[survey.slug]))
    assert response.status_code == 302
    response = client.get(reverse("surveys:preview_step", args=[survey.slug, 1]))
    assert response.status_code == 200
    assert b"Preview mode" in response.content

    response = client.post(
        reverse("surveys:preview_step", args=[survey.slug, 1]),
        {"value": remote.id},
    )
    assert response.status_code == 302
    assert response["Location"].endswith(
        reverse("surveys:preview_step", args=[survey.slug, q3.order])
    )
    assert survey.responses.count() == 0


@pytest.mark.django_db
def test_preview_unknown_step_redirects(client, branching_survey, staff_user):
    survey, *_ = branching_survey
    client.force_login(staff_user)
    response = client.get(reverse("surveys:preview_step", args=[survey.slug, 99]))
    assert response.status_code == 302


@pytest.mark.django_db
def test_preview_unpublished_survey(staff_user, unpublished_survey, client):
    from apps.surveys.models import Question

    Question.objects.create(
        survey=unpublished_survey,
        order=1,
        text="Draft question",
        type=Question.Type.SHORT_TEXT,
    )
    client.force_login(staff_user)
    response = client.get(reverse("surveys:preview_step", args=[unpublished_survey.slug, 1]))
    assert response.status_code == 200
    assert b"Preview mode" in response.content


@pytest.mark.django_db
def test_results_dashboard_raw_and_exports(client, branching_survey, staff_user):
    survey, q1, _q2, q3, remote = branching_survey
    survey_response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(survey_response, q1, {"value": remote})
    ResponseRepository.save_answer(survey_response, q3, {"value": q3.choices.get(label="5")})
    ResponseRepository.complete(survey_response)
    client.force_login(staff_user)

    response = client.get(reverse("surveys:results", args=[survey.id]))
    assert response.status_code == 200
    assert b"Completion" in response.content

    response = client.get(
        reverse("surveys:results_raw", args=[survey.id]),
        {"q": "nothing"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert b"No responses found" in response.content

    response = client.get(reverse("surveys:export_csv", args=[survey.id]))
    assert response.status_code == 200
    assert "text/csv" in response["Content-Type"]
    assert str(survey_response.uuid).encode() in response.content

    response = client.get(reverse("surveys:export_json", args=[survey.id]))
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload[0]["response"]["uuid"] == str(survey_response.uuid)


@pytest.mark.django_db
def test_results_require_staff(client, branching_survey, regular_user):
    survey, *_ = branching_survey
    response = client.get(reverse("surveys:results", args=[survey.id]))
    assert response.status_code == 302
    client.force_login(regular_user)
    response = client.get(reverse("surveys:results", args=[survey.id]))
    assert response.status_code == 302


@pytest.mark.django_db
def test_results_unknown_survey_404(staff_user, client):
    client.force_login(staff_user)
    response = client.get(reverse("surveys:results", args=[99999]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_results_raw_search_finds_choice_label(client, branching_survey, staff_user):
    survey, q1, _q2, _q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": remote})
    client.force_login(staff_user)

    page = client.get(
        reverse("surveys:results_raw", args=[survey.id]),
        {"q": "Remote"},
    )
    assert page.status_code == 200
    assert str(response.uuid).encode() in page.content


@pytest.mark.django_db
def test_results_raw_pagination(client, branching_survey, staff_user):
    survey, q1, _q2, _q3, remote = branching_survey
    for _ in range(30):
        r = ResponseRepository.start(survey)
        ResponseRepository.save_answer(r, q1, {"value": remote})
    client.force_login(staff_user)
    page = client.get(reverse("surveys:results_raw", args=[survey.id]), {"page": 2})
    assert page.status_code == 200
    assert b"Page 2" in page.content

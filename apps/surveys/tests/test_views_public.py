import pytest
from apps.surveys.repositories import ResponseRepository
from django.urls import reverse


@pytest.mark.django_db
def test_survey_list_shows_published_only(client, branching_survey, unpublished_survey):
    survey, *_ = branching_survey
    response = client.get(reverse("surveys:list"))
    assert response.status_code == 200
    assert survey.title.encode() in response.content
    assert unpublished_survey.title.encode() not in response.content


@pytest.mark.django_db
def test_survey_list_empty_state(client, db):
    response = client.get(reverse("surveys:list"))
    assert response.status_code == 200
    assert b"No published surveys" in response.content


@pytest.mark.django_db
def test_survey_intro_renders(client, branching_survey):
    survey, *_ = branching_survey
    response = client.get(reverse("surveys:intro", args=[survey.slug]))
    assert response.status_code == 200
    assert survey.title.encode() in response.content


@pytest.mark.django_db
def test_survey_intro_shows_continue_for_in_progress(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    response = client.get(reverse("surveys:intro", args=[survey.slug]))
    assert b"Continue" in response.content


@pytest.mark.django_db
def test_unpublished_survey_returns_404(client, unpublished_survey):
    response = client.get(reverse("surveys:intro", args=[unpublished_survey.slug]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_unknown_survey_slug_returns_404(client, db):
    response = client.get(reverse("surveys:intro", args=["does-not-exist"]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_start_survey_requires_post(client, branching_survey):
    survey, *_ = branching_survey
    response = client.get(reverse("surveys:start", args=[survey.slug]))
    assert response.status_code == 405


@pytest.mark.django_db
def test_step_requires_session(client, branching_survey):
    survey, *_ = branching_survey
    response = client.get(reverse("surveys:step", args=[survey.slug, 1]))
    assert response.status_code == 302
    assert reverse("surveys:intro", args=[survey.slug]) in response["Location"]


@pytest.mark.django_db
def test_done_page_renders(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    survey_response = survey.responses.get()
    ResponseRepository.save_answer(survey_response, q1, {"value": remote})
    ResponseRepository.save_answer(
        survey_response, q3, {"value": q3.choices.get(label="3")}
    )
    ResponseRepository.complete(survey_response)
    response = client.get(reverse("surveys:done", args=[survey.slug]))
    assert response.status_code == 200
    assert b"Thanks" in response.content


@pytest.mark.django_db
def test_survey_happy_path(client, branching_survey):
    survey, _q1, _q2, q3, remote = branching_survey

    response = client.get(reverse("surveys:intro", args=[survey.slug]))
    assert response.status_code == 200

    response = client.post(reverse("surveys:start", args=[survey.slug]))
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:step", args=[survey.slug, 1]))

    response = client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": remote.id})
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:step", args=[survey.slug, q3.order]))


@pytest.mark.django_db
def test_htmx_validation_returns_partial(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))

    response = client.post(
        reverse("surveys:step", args=[survey.slug, 1]),
        {},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 422
    assert b"<html" not in response.content
    assert b"This field is required" in response.content


@pytest.mark.django_db
def test_favicon_redirect(client):
    response = client.get("/favicon.ico")
    assert response.status_code in (301, 302)

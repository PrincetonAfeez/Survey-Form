import pytest
from apps.surveys.repositories import ResponseRepository
from django.urls import reverse


@pytest.mark.django_db
def test_step_get_includes_resume_link(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    response = client.get(reverse("surveys:step", args=[survey.slug, 1]))
    assert response.status_code == 200
    assert b"Resume link" in response.content


@pytest.mark.django_db
def test_preview_step_htmx_validation(client, branching_survey, staff_user):
    survey, *_ = branching_survey
    client.force_login(staff_user)
    response = client.post(
        reverse("surveys:preview_step", args=[survey.slug, 1]),
        {},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 422


@pytest.mark.django_db
def test_preview_step_htmx_success_redirect(client, branching_survey, staff_user):
    survey, _q1, _q2, q3, remote = branching_survey
    client.force_login(staff_user)
    client.post(
        reverse("surveys:preview_step", args=[survey.slug, 1]),
        {"value": remote.id},
        HTTP_HX_REQUEST="true",
    )
    response = client.post(
        reverse("surveys:preview_step", args=[survey.slug, q3.order]),
        {"value": q3.choices.get(label="5").id},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 204
    assert "HX-Redirect" in response


@pytest.mark.django_db
def test_export_csv_empty_survey(staff_user, branching_survey, client):
    survey, *_ = branching_survey
    client.force_login(staff_user)
    response = client.get(reverse("surveys:export_csv", args=[survey.id]))
    assert response.status_code == 200
    assert b"response_uuid" in response.content


@pytest.mark.django_db
def test_step_unknown_question_404(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    response = client.get(reverse("surveys:step", args=[survey.slug, 99]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_filter_by_answer_query_date_match(full_survey, staff_user, client):
    from datetime import date

    survey = full_survey["survey"]
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, full_survey["date"], {"value": date(2026, 6, 1)})
    client.force_login(staff_user)
    page = client.get(
        reverse("surveys:results_raw", args=[survey.id]),
        {"q": "2026-06-01"},
    )
    assert page.status_code == 200
    assert str(response.uuid).encode() in page.content


@pytest.mark.django_db
def test_question_admin_short_text(branching_survey):
    from apps.surveys.admin import QuestionAdmin
    from django.contrib.admin.sites import AdminSite

    survey, q1, *_ = branching_survey
    admin = QuestionAdmin(q1.__class__, AdminSite())
    assert q1.text[:80] == admin.short_text(q1)

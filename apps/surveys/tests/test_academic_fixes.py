"""Regression tests for academic-scope bug fixes"""

import pytest
from apps.surveys.models import Question, Response, Survey
from apps.surveys.repositories import ResponseRepository
from apps.surveys.views import (
    _csv_safe,
    _path_step_back,
    _resolve_step_from_path,
    _valid_path_question_ids,
)
from django.urls import reverse
from django.utils import timezone


@pytest.mark.django_db
def test_csv_safe_prefixes_formula_like_values():
    assert _csv_safe("=SUM(1+1)") == "'=SUM(1+1)"
    assert _csv_safe("hello") == "hello"
    assert _csv_safe(None) == ""


@pytest.mark.django_db
def test_completion_seconds_never_negative(branching_survey):
    survey, *_ = branching_survey
    response = ResponseRepository.start(survey)
    response.completed_at = response.started_at - timezone.timedelta(hours=1)
    assert response.completion_seconds == 0


@pytest.mark.django_db
def test_path_step_back_shortens_path_when_previous_question_deleted(branching_survey):
    survey, q1, q2, q3, _remote = branching_survey
    deleted_id = q2.id
    q2.delete()
    path = [q1.id, deleted_id, q3.id]
    previous, new_path = _path_step_back(survey, path, q3.order)
    assert previous is None
    assert new_path == [q1.id]


@pytest.mark.django_db
def test_path_step_back_skips_deleted_previous_question(branching_survey):
    survey, q1, q2, q3, _remote = branching_survey
    path = [q1.id, q2.id, q3.id]
    q2.delete()
    path = _valid_path_question_ids(survey, path)
    previous, new_path = _path_step_back(survey, path, q3.order)
    assert previous == q1.order
    assert q2.id not in new_path


@pytest.mark.django_db
def test_resolve_step_from_path_after_tail_deleted(branching_survey):
    survey, q1, q2, _q3, _remote = branching_survey
    path = [q1.id, q2.id]
    q2.delete()
    assert _resolve_step_from_path(survey, path) == q1.order


@pytest.mark.django_db
def test_export_csv_uses_snapshot_header(staff_user, client, full_survey):
    survey = full_survey["survey"]
    short = full_survey["short"]
    short.text = "Live label"
    short.save()
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, short, {"value": "Ada"})
    ResponseRepository.complete(response)
    short.text = "Changed label"
    short.save()

    client.force_login(staff_user)
    result = client.get(reverse("surveys:export_csv", args=[survey.id]))
    assert result.status_code == 200
    body = result.content.decode()
    header = body.split("\n")[0]
    assert "Ada" in body
    assert "Live label" in header
    assert "Changed label" not in header


@pytest.mark.django_db
def test_preview_redirects_home_when_resolve_returns_none(
    staff_user, client, branching_survey, monkeypatch
):
    survey, q1, q2, q3, _remote = branching_survey
    client.force_login(staff_user)
    client.get(reverse("surveys:preview", args=[survey.slug]))
    monkeypatch.setattr("apps.surveys.views._resolve_step_from_path", lambda *_args: None)
    response = client.get(reverse("surveys:preview_step", args=[survey.slug, q3.order]))
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:preview", args=[survey.slug]))


@pytest.mark.django_db
def test_resolve_step_from_path_returns_none_without_questions():
    survey = Survey.objects.create(title="Empty", slug="empty-resolve", is_published=False)
    assert _resolve_step_from_path(survey, [99999]) is None


@pytest.mark.django_db
def test_ensure_path_rebuilds_twice_when_survey_has_no_questions():
    from apps.surveys.views import _ensure_path, _path_key
    from django.test import RequestFactory

    survey = Survey.objects.create(title="Empty", slug="empty-path", is_published=False)
    response = Response.objects.create(survey=survey, current_step=1)
    request = RequestFactory().get("/")
    request.session = {_path_key(survey): [99999]}
    assert _ensure_path(request, survey, response) == []


@pytest.mark.django_db
def test_ensure_path_rebuilds_twice_when_session_path_is_all_invalid(branching_survey):
    from apps.surveys.views import _ensure_path, _path_key
    from django.test import RequestFactory

    survey, q1, *_rest = branching_survey
    response = ResponseRepository.start(survey)
    request = RequestFactory().get("/")
    request.session = {_path_key(survey): [99999, 88888]}
    path = _ensure_path(request, survey, response)
    assert path == [q1.id]


@pytest.mark.django_db
def test_ensure_path_rebuilds_when_session_has_only_deleted_ids(branching_survey):
    from apps.surveys.views import _ensure_path, _path_key
    from django.test import RequestFactory

    survey, q1, q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": remote})
    q2.delete()
    request = RequestFactory().get("/")
    request.session = {_path_key(survey): [q1.id, q2.id, q3.id]}
    path = _ensure_path(request, survey, response)
    assert q2.id not in path
    assert q1.id in path


@pytest.mark.django_db
def test_record_forward_appends_from_when_tail_differs(branching_survey):
    from apps.surveys.views import _get_path, _path_key, _record_forward
    from django.test import RequestFactory

    survey, q1, q2, q3, _remote = branching_survey
    request = RequestFactory().get("/")
    request.session = {_path_key(survey): [q1.id]}
    _record_forward(request, survey, q2, q3, preview=False)
    assert _get_path(request, survey) == [q1.id, q2.id, q3.id]


@pytest.mark.django_db
def test_rating_resave_keeps_scale_choices():
    from apps.surveys.signals import RATING_LABELS

    survey = Survey.objects.create(title="Sig", slug="sig-resave")
    question = Question.objects.create(
        survey=survey, order=1, text="Stars", type=Question.Type.RATING
    )
    question.save()
    assert list(question.choices.order_by("order").values_list("label", flat=True)) == RATING_LABELS

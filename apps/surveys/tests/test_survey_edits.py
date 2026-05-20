"""Survey mutation during in-flight responses (issues 5–10)."""

import pytest
from apps.surveys.constants import LONG_TEXT_MAX_LENGTH, SHORT_TEXT_MAX_LENGTH
from apps.surveys.forms import form_for_question
from apps.surveys.models import Question, Response, Survey
from apps.surveys.pathing import build_path_from_response
from apps.surveys.repositories import ResponseRepository, SurveyRepository
from django.core.exceptions import ValidationError
from django.urls import reverse


@pytest.mark.django_db
def test_answer_stores_question_text_snapshot(branching_survey):
    survey, q1, *_q2, _q3, remote = branching_survey
    q1.text = "Original wording"
    q1.save()
    response = ResponseRepository.start(survey)
    answer = ResponseRepository.save_answer(response, q1, {"value": remote})
    assert answer.question_text_snapshot == "Original wording"

    q1.text = "Edited wording"
    q1.save()
    answer.refresh_from_db()
    assert answer.question_label == "Original wording"


@pytest.mark.django_db
def test_step_shows_snapshot_text_when_revisiting(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    q1.text = "Original"
    q1.save()
    client.post(reverse("surveys:start", args=[survey.slug]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": remote.id})
    q1.text = "Edited"
    q1.save()
    page = client.get(reverse("surveys:step", args=[survey.slug, q1.order]))
    assert b"Original" in page.content
    assert b"Edited" not in page.content


@pytest.mark.django_db
def test_build_path_keeps_answered_question_after_reorder(branching_survey):
    survey, q1, q2, _q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": remote})
    ResponseRepository.move_to_step(response, q2.order)
    q1.order = 5
    q1.save()
    path = build_path_from_response(survey, response)
    assert q1.id in path


@pytest.mark.django_db
def test_resume_repairs_missing_current_step(client, branching_survey):
    survey, q1, q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": remote})
    response.current_step = q2.order
    response.save(update_fields=["current_step"])
    q2.delete()
    from apps.surveys.tokens import issue_resume_token

    token = issue_resume_token(response)
    result = client.get(reverse("surveys:resume", args=[survey.slug, token]))
    assert result.status_code == 302
    assert result["Location"].endswith(reverse("surveys:step", args=[survey.slug, q3.order]))


@pytest.mark.django_db
def test_unpublished_survey_shows_friendly_page(client, branching_survey):
    survey, *_ = branching_survey
    survey.is_published = False
    survey.save()
    response = client.get(reverse("surveys:intro", args=[survey.slug]))
    assert response.status_code == 403
    assert b"no longer accepting responses" in response.content


@pytest.mark.django_db
def test_short_text_form_rejects_oversized_input(full_survey):
    huge = "x" * (SHORT_TEXT_MAX_LENGTH + 1)
    form = form_for_question(full_survey["short"], data={"value": huge})
    assert form.is_valid() is False
    assert "value" in form.errors


@pytest.mark.django_db
def test_short_text_save_answer_rejects_oversized_input(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    huge = "x" * (SHORT_TEXT_MAX_LENGTH + 1)
    with pytest.raises(ValidationError):
        ResponseRepository.save_answer(response, full_survey["short"], {"value": huge})


@pytest.mark.django_db
def test_long_text_save_answer_rejects_oversized_input(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    huge = "x" * (LONG_TEXT_MAX_LENGTH + 1)
    with pytest.raises(ValidationError):
        ResponseRepository.save_answer(response, full_survey["long"], {"value": huge})


@pytest.mark.django_db
def test_resume_works_for_unrelated_newer_draft(client, branching_survey):
    """Another respondent's draft must not invalidate an earlier resume token."""
    from apps.surveys.tokens import issue_resume_token

    survey, *_ = branching_survey
    earlier = ResponseRepository.start(survey)
    token = issue_resume_token(earlier)
    ResponseRepository.start(survey)
    response = client.get(reverse("surveys:resume", args=[survey.slug, token]))
    assert response.status_code == 302
    assert reverse("surveys:step", args=[survey.slug, earlier.current_step]) in response["Location"]


@pytest.mark.django_db
def test_resume_rejects_stale_token_when_session_has_newer_draft(client, branching_survey):
    from apps.surveys.tokens import issue_resume_token
    from apps.surveys.views import _session_key

    survey, *_ = branching_survey
    earlier = ResponseRepository.start(survey)
    token = issue_resume_token(earlier)
    later = ResponseRepository.start(survey)
    session = client.session
    session[_session_key(survey)] = str(later.uuid)
    session.save()
    response = client.get(reverse("surveys:resume", args=[survey.slug, token]))
    assert response.status_code == 400


@pytest.mark.django_db
def test_long_text_form_rejects_oversized_input(full_survey):
    huge = "x" * (LONG_TEXT_MAX_LENGTH + 1)
    form = form_for_question(full_survey["long"], data={"value": huge})
    assert form.is_valid() is False
    assert "value" in form.errors


@pytest.mark.django_db
def test_force_new_deletes_previous_session_draft(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    first_uuid = survey.responses.get().uuid
    for _ in range(3):
        client.post(
            reverse("surveys:start", args=[survey.slug]),
            {"force_new": "1"},
        )
    assert survey.responses.count() == 1
    assert survey.responses.get().uuid != first_uuid


@pytest.mark.django_db
def test_sync_current_step_falls_back_to_first_question(branching_survey):
    survey, q1, *_ = branching_survey
    response = Response.objects.create(survey=survey, current_step=99)
    step = ResponseRepository.sync_current_step(survey, response)
    assert step == q1.order


@pytest.mark.django_db
def test_get_question_by_id(branching_survey):
    survey, q1, *_ = branching_survey
    assert SurveyRepository.get_question_by_id(survey, q1.id) == q1
    assert SurveyRepository.get_question_by_id(survey, 99999) is None


@pytest.mark.django_db
def test_unpublished_blocks_respondent_views(client, unpublished_survey):
    Question.objects.create(
        survey=unpublished_survey,
        order=1,
        text="Q",
        type=Question.Type.SHORT_TEXT,
    )
    slug = unpublished_survey.slug
    assert client.post(reverse("surveys:start", args=[slug])).status_code == 403
    assert client.get(reverse("surveys:step", args=[slug, 1])).status_code == 403
    assert client.get(reverse("surveys:done", args=[slug])).status_code == 403
    token = "invalid"
    assert client.get(reverse("surveys:resume", args=[slug, token])).status_code == 403
    assert client.get(reverse("surveys:step_back", args=[slug, 1])).status_code == 403


@pytest.mark.django_db
def test_sync_current_step_raises_when_survey_has_no_questions(db):
    survey = Survey.objects.create(title="Gone", slug="gone-q", is_published=False)
    Survey.objects.filter(pk=survey.pk).update(is_published=True)
    survey.refresh_from_db()
    response = Response.objects.create(survey=survey, current_step=1)
    with pytest.raises(ValueError, match="no questions"):
        ResponseRepository.sync_current_step(survey, response)

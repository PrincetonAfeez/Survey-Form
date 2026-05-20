"""Survey mutation during in-flight responses (issues 5–10)."""

import pytest
from apps.surveys.constants import LONG_TEXT_MAX_LENGTH
from apps.surveys.models import Question, Response, Survey
from apps.surveys.pathing import build_path_from_response
from apps.surveys.repositories import ResponseRepository, SurveyRepository
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
def test_short_text_rejects_oversized_input(full_survey):
    from apps.surveys.constants import SHORT_TEXT_MAX_LENGTH

    response = ResponseRepository.start(full_survey["survey"])
    huge = "x" * (SHORT_TEXT_MAX_LENGTH + 1)
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        ResponseRepository.save_answer(response, full_survey["short"], {"value": huge})


@pytest.mark.django_db
def test_resume_rejects_orphan_when_newer_draft_exists(client, branching_survey):
    from apps.surveys.tokens import issue_resume_token

    survey, *_ = branching_survey
    orphan = ResponseRepository.start(survey)
    token = issue_resume_token(orphan)
    ResponseRepository.start(survey)
    response = client.get(reverse("surveys:resume", args=[survey.slug, token]))
    assert response.status_code == 400


@pytest.mark.django_db
def test_long_text_rejects_oversized_input(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    huge = "x" * (LONG_TEXT_MAX_LENGTH + 1)
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        ResponseRepository.save_answer(response, full_survey["long"], {"value": huge})


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
    survey = Survey.objects.create(title="Gone", slug="gone-q", is_published=True)
    response = Response.objects.create(survey=survey, current_step=1)
    with pytest.raises(ValueError, match="no questions"):
        ResponseRepository.sync_current_step(survey, response)


@pytest.mark.django_db
def test_purge_old_drafts_command():
    from django.core.management import call_command

    survey = Survey.objects.create(title="Old", slug="old-drafts", is_published=True)
    Question.objects.create(
        survey=survey, order=1, text="Q", type=Question.Type.SHORT_TEXT
    )
    ResponseRepository.start(survey)
    from apps.surveys.models import Response
    from django.utils import timezone
    from datetime import timedelta

    Response.objects.filter(survey=survey).update(
        started_at=timezone.now() - timedelta(days=60)
    )
    call_command("purge_old_drafts", days=30)
    assert Response.objects.filter(survey=survey).count() == 0

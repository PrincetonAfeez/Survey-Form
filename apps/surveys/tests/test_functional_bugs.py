""" Regression tests for functional bugs A.1–A.3 """

import pytest
from apps.surveys.models import BranchRule, Question, Survey
from apps.surveys.repositories import ResponseRepository, SurveyRepository
from django.core.exceptions import ValidationError
from django.urls import reverse


@pytest.fixture
def non_one_start_survey(db):
    survey = Survey.objects.create(title="Offset orders", slug="offset-orders", is_published=False)
    q10 = Question.objects.create(
        survey=survey,
        order=10,
        text="First (order 10)?",
        type=Question.Type.SHORT_TEXT,
    )
    Question.objects.create(
        survey=survey,
        order=20,
        text="Second (order 20)?",
        type=Question.Type.SHORT_TEXT,
        is_required=False,
    )
    survey.is_published = True
    survey.save()
    return survey, q10


@pytest.mark.django_db
def test_first_question_order_not_hardcoded_to_one(non_one_start_survey):
    survey, q10 = non_one_start_survey
    assert SurveyRepository.first_question_order(survey) == 10
    response = ResponseRepository.start(survey)
    assert response.current_step == 10


@pytest.mark.django_db
def test_wizard_starts_at_first_question_order(client, non_one_start_survey):
    survey, q10 = non_one_start_survey
    response = client.post(reverse("surveys:start", args=[survey.slug]))
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:step", args=[survey.slug, q10.order]))

    page = client.get(reverse("surveys:step", args=[survey.slug, q10.order]))
    assert page.status_code == 200
    assert b"First (order 10)" in page.content


@pytest.mark.django_db
def test_preview_starts_at_first_question_order(client, non_one_start_survey, staff_user):
    survey, q10 = non_one_start_survey
    client.force_login(staff_user)
    response = client.get(reverse("surveys:preview", args=[survey.slug]))
    assert response.status_code == 302
    assert response["Location"].endswith(
        reverse("surveys:preview_step", args=[survey.slug, q10.order])
    )

    page = client.get(reverse("surveys:preview_step", args=[survey.slug, q10.order]))
    assert page.status_code == 200
    assert b"Preview mode" in page.content


@pytest.mark.django_db
def test_start_raises_when_survey_has_no_questions(db):
    survey = Survey.objects.create(title="Empty", slug="empty-start", is_published=False)
    Survey.objects.filter(pk=survey.pk).update(is_published=True)
    survey.refresh_from_db()
    with pytest.raises(ValueError, match="no questions"):
        ResponseRepository.start(survey)


@pytest.mark.django_db
def test_branch_rule_rejects_self_referential_next_question(branching_survey):
    survey, q1, _q2, _q3, remote = branching_survey
    rule = BranchRule(question=q1, choice=remote, next_question=q1)
    with pytest.raises(ValidationError) as exc:
        rule.full_clean()
    assert "next_question" in exc.value.error_dict


@pytest.mark.django_db
def test_question_clean_requires_choices_for_single_choice():
    survey = Survey.objects.create(title="S", slug="choices-req")
    question = Question.objects.create(
        survey=survey,
        order=1,
        text="Pick one",
        type=Question.Type.SINGLE_CHOICE,
    )
    with pytest.raises(ValidationError) as exc:
        question.full_clean()
    assert "type" in exc.value.error_dict


@pytest.mark.django_db
def test_survey_clean_blocks_publish_without_choices():
    survey = Survey.objects.create(title="Pub", slug="pub-no-choices", is_published=False)
    Question.objects.create(
        survey=survey,
        order=1,
        text="Pick",
        type=Question.Type.MULTIPLE_CHOICE,
    )
    survey.is_published = True
    with pytest.raises(ValidationError) as exc:
        survey.full_clean()
    assert "is_published" in exc.value.error_dict


@pytest.mark.django_db
def test_survey_clean_allows_publish_when_rating_auto_seeded():
    survey = Survey.objects.create(title="Rate", slug="pub-rating", is_published=False)
    Question.objects.create(
        survey=survey,
        order=1,
        text="Stars",
        type=Question.Type.RATING,
    )
    survey.is_published = True
    survey.full_clean()


@pytest.mark.django_db
def test_survey_clean_skips_questions_when_unsaved_draft():
    survey = Survey(title="Unsaved", slug="unsaved", is_published=False)
    survey.full_clean()


@pytest.mark.django_db
def test_survey_clean_allows_publish_flag_before_save():
    survey = Survey(title="New", slug="new-unsaved", is_published=True)
    survey.full_clean()


@pytest.mark.django_db
def test_survey_clean_blocks_publish_with_no_questions():
    survey = Survey.objects.create(title="Empty", slug="pub-empty", is_published=False)
    survey.is_published = True
    with pytest.raises(ValidationError) as exc:
        survey.save()
    assert "is_published" in exc.value.error_dict

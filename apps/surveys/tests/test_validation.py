""" Tests for surveys app validation """

import pytest
from django.core.exceptions import ValidationError

from apps.surveys.constants import LONG_TEXT_MAX_LENGTH, SHORT_TEXT_MAX_LENGTH
from apps.surveys.forms import form_for_question
from apps.surveys.models import Question, Survey
from apps.surveys.repositories import ResponseRepository
from apps.surveys.validation import (
    validate_answer_value,
    validate_survey,
    validate_survey_after_save,
)


@pytest.mark.django_db
def test_validate_survey_blocks_publish_without_questions():
    survey = Survey.objects.create(title="Empty", slug="empty-val", is_published=False)
    survey.is_published = True
    errors = validate_survey(survey)
    assert "is_published" in errors


@pytest.mark.django_db
def test_survey_save_rejects_published_without_questions():
    with pytest.raises(ValidationError):
        Survey.objects.create(title="Empty", slug="empty-save", is_published=True)


@pytest.mark.django_db
def test_validate_survey_after_save_closes_orm_create_gap(branching_survey):
    survey, *_ = branching_survey
    survey.questions.all().delete()
    errors = validate_survey_after_save(survey)
    assert "is_published" in errors


@pytest.mark.django_db
def test_form_and_repository_share_text_limits(full_survey):
    huge = "x" * (SHORT_TEXT_MAX_LENGTH + 1)
    form = form_for_question(full_survey["short"], data={"value": huge})
    assert not form.is_valid()
    assert validate_answer_value(full_survey["short"], huge) is not None

    response = ResponseRepository.start(full_survey["survey"])
    with pytest.raises(ValidationError):
        ResponseRepository.save_answer(response, full_survey["short"], {"value": huge})


@pytest.mark.django_db
def test_validate_answer_value_long_text(full_survey):
    huge = "x" * (LONG_TEXT_MAX_LENGTH + 1)
    message = validate_answer_value(full_survey["long"], huge)
    assert message is not None
    assert str(LONG_TEXT_MAX_LENGTH) in message

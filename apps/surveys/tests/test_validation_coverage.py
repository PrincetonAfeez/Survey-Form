"""Coverage for validation.py, resume policy, schema export, and management command tests"""

from unittest.mock import patch

import pytest
from apps.surveys.constants import LONG_TEXT_MAX_LENGTH
from apps.surveys.forms import form_for_question
from apps.surveys.models import Question
from apps.surveys.repositories import ResponseRepository
from apps.surveys.schema_contract import (
    WIZARD_ANSWER_SCHEMA_PATH,
    export_wizard_answer,
    validate_json,
)
from apps.surveys.validation import validate_answer_value
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
def test_form_clean_adds_domain_validation_error(full_survey):
    form = form_for_question(full_survey["number"], data={})
    assert not form.is_valid()
    assert "value" in form.errors

    huge = "x" * (LONG_TEXT_MAX_LENGTH + 1)
    long_form = form_for_question(full_survey["long"], data={"value": huge})
    assert not long_form.is_valid()
    assert "value" in long_form.errors

    with patch("apps.surveys.forms.validate_answer_value", return_value="Domain rule"):
        short_form = form_for_question(full_survey["short"], data={"value": "ok"})
        assert not short_form.is_valid()
        assert "Domain rule" in str(short_form.errors)


@pytest.mark.django_db
def test_validate_answer_value_required_types(full_survey):
    assert validate_answer_value(full_survey["short"], "") is not None
    assert validate_answer_value(full_survey["number"], None) is not None
    assert validate_answer_value(full_survey["date"], None) is not None
    assert validate_answer_value(full_survey["likert"], None) is not None
    assert validate_answer_value(full_survey["rating"], None) is not None
    assert validate_answer_value(full_survey["multi"], []) is not None


@pytest.mark.django_db
def test_is_resume_allowed_invalid_session_uuid(branching_survey):
    survey, *_ = branching_survey
    response = ResponseRepository.start(survey)
    assert ResponseRepository.is_resume_allowed(response, "not-a-uuid") is True


@pytest.mark.django_db
def test_is_resume_allowed_unknown_session_response(branching_survey):
    survey, *_ = branching_survey
    response = ResponseRepository.start(survey)
    assert (
        ResponseRepository.is_resume_allowed(response, "00000000-0000-0000-0000-000000000099")
        is True
    )


@pytest.mark.django_db
def test_is_resume_allowed_other_survey_session(branching_survey):
    from apps.surveys.models import Survey

    survey, *_ = branching_survey
    response = ResponseRepository.start(survey)
    other = Survey.objects.create(title="O", slug="o-resume", is_published=False)
    Question.objects.create(survey=other, order=1, text="Q", type=Question.Type.SHORT_TEXT)
    other.is_published = True
    other.save()
    other_response = ResponseRepository.start(other)
    assert ResponseRepository.is_resume_allowed(response, str(other_response.uuid)) is True


@pytest.mark.django_db
def test_export_wizard_answer_all_shapes(full_survey):
    assert "text" in export_wizard_answer(full_survey["short"], "hi")
    assert export_wizard_answer(full_survey["long"], "story")["text"] == "story"
    assert export_wizard_answer(full_survey["number"], None)["number"] is None
    assert "date" in export_wizard_answer(full_survey["date"], None)
    choice = full_survey["rating"].choices.first()
    assert export_wizard_answer(full_survey["rating"], choice)["choice_id"] == choice.pk
    assert export_wizard_answer(full_survey["multi"], [])["choice_ids"] == []


@pytest.mark.django_db
def test_export_survey_schema_command(branching_survey, capsys):
    survey, *_ = branching_survey
    call_command("export_survey_schema", survey.slug, "--validate")
    assert survey.slug in capsys.readouterr().out


@pytest.mark.django_db
def test_export_survey_schema_command_errors(branching_survey):
    with pytest.raises(CommandError, match="No survey"):
        call_command("export_survey_schema", "no-such-slug")

    survey, *_ = branching_survey
    with (
        patch(
            "apps.surveys.management.commands.export_survey_schema.validate_json",
            return_value=["bad field"],
        ),
        pytest.raises(CommandError, match="Schema validation failed"),
    ):
        call_command("export_survey_schema", survey.slug, "--validate")


def test_validate_json_without_jsonschema(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "jsonschema":
            raise ImportError
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert validate_json({}, WIZARD_ANSWER_SCHEMA_PATH) == []

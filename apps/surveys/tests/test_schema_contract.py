""" Tests for surveys app schema contract """

import pytest

from apps.surveys.schema_contract import (
    SURVEY_DEFINITION_SCHEMA_PATH,
    export_survey_definition,
    export_wizard_answer,
    validate_json,
)


@pytest.mark.django_db
def test_export_survey_definition_matches_schema(branching_survey):
    survey, *_ = branching_survey
    payload = export_survey_definition(survey)
    assert payload["slug"] == survey.slug
    assert payload["questions"]
    errors = validate_json(payload, SURVEY_DEFINITION_SCHEMA_PATH)
    assert errors == []


@pytest.mark.django_db
def test_export_wizard_answer_shapes(branching_survey):
    survey, q1, *_ = branching_survey
    choice = q1.choices.first()
    payload = export_wizard_answer(q1, choice)
    assert payload["question_type"] == "single_choice"
    assert payload["choice_id"] == choice.pk

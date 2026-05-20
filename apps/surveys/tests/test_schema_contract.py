"""Tests for surveys app schema contract"""

import pytest
from apps.surveys.models import Question, Survey
from apps.surveys.schema_contract import (
    SURVEY_DEFINITION_SCHEMA_PATH,
    WIZARD_ANSWER_SCHEMA_PATH,
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


@pytest.mark.django_db
def test_export_wizard_answer_likert_emits_choice_id():
    """LIKERT is choice-based; the wizard export must include choice_id (regression)."""
    survey = Survey.objects.create(title="L", slug="likert-export")
    likert = Question.objects.create(
        survey=survey, order=1, text="Agree?", type=Question.Type.LIKERT
    )
    choice = likert.choices.get(label="Agree")
    payload = export_wizard_answer(likert, choice)
    assert payload["question_type"] == "likert"
    assert payload["choice_id"] == choice.pk


@pytest.mark.django_db
def test_wizard_answer_schema_rejects_mismatched_fields():
    """Tightened schema enforces per-question_type field shapes."""
    # number question shouldn't carry choice_ids
    errors = validate_json(
        {"question_order": 1, "question_type": "number", "number": "5", "choice_ids": [1]},
        WIZARD_ANSWER_SCHEMA_PATH,
    )
    assert errors

    # likert without choice_id is invalid
    errors = validate_json(
        {"question_order": 1, "question_type": "likert"},
        WIZARD_ANSWER_SCHEMA_PATH,
    )
    assert errors

    # likert + choice_id is valid
    errors = validate_json(
        {"question_order": 1, "question_type": "likert", "choice_id": 3},
        WIZARD_ANSWER_SCHEMA_PATH,
    )
    assert errors == []


@pytest.mark.django_db
def test_export_wizard_answer_likert_payload_matches_schema():
    """Round-trip: LIKERT export should pass the tightened schema."""
    survey = Survey.objects.create(title="LR", slug="likert-rt")
    likert = Question.objects.create(
        survey=survey, order=1, text="Agree?", type=Question.Type.LIKERT
    )
    choice = likert.choices.get(label="Strongly agree")
    payload = export_wizard_answer(likert, choice)
    errors = validate_json(payload, WIZARD_ANSWER_SCHEMA_PATH)
    assert errors == []

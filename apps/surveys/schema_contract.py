""" JSON Schema contract aligned with the Django survey models """
"""
Schemas live in ``Schema/`` at the repo root. This module exports survey definitions
and validates export payloads against those schemas (optional ``jsonschema``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings

from .constants import LONG_TEXT_MAX_LENGTH, SHORT_TEXT_MAX_LENGTH
from .models import Question, Survey

SCHEMA_DIR = Path(settings.BASE_DIR) / "Schema"
SURVEY_DEFINITION_SCHEMA_PATH = SCHEMA_DIR / "django-survey-definition.schema.json"
WIZARD_ANSWER_SCHEMA_PATH = SCHEMA_DIR / "django-wizard-answer.schema.json"

QUESTION_TYPE_SCHEMA_MAP = {
    Question.Type.SHORT_TEXT: "short_text",
    Question.Type.LONG_TEXT: "long_text",
    Question.Type.SINGLE_CHOICE: "single_choice",
    Question.Type.MULTIPLE_CHOICE: "multiple_choice",
    Question.Type.RATING: "rating",
    Question.Type.LIKERT: "likert",
    Question.Type.DATE: "date",
    Question.Type.NUMBER: "number",
}


def export_survey_definition(survey: Survey) -> dict[str, Any]:
    """Serialize a survey to JSON matching ``Schema/django-survey-definition.schema.json``."""
    questions = []
    for question in survey.questions.prefetch_related("choices", "branch_rules").order_by(
        "order"
    ):
        entry: dict[str, Any] = {
            "order": question.order,
            "text": question.text,
            "type": QUESTION_TYPE_SCHEMA_MAP[question.type],
            "is_required": question.is_required,
        }
        if question.accepts_choices:
            entry["choices"] = [
                {"order": choice.order, "label": choice.label}
                for choice in question.choices.all()
            ]
        if question.type == Question.Type.SINGLE_CHOICE:
            entry["branch_rules"] = [
                {
                    "choice_order": rule.choice.order,
                    "next_question_order": rule.next_question.order,
                }
                for rule in question.branch_rules.select_related(
                    "choice", "next_question"
                )
            ]
        questions.append(entry)

    return {
        "title": survey.title,
        "slug": survey.slug,
        "intro": survey.intro,
        "is_published": survey.is_published,
        "limits": {
            "short_text_max_length": SHORT_TEXT_MAX_LENGTH,
            "long_text_max_length": LONG_TEXT_MAX_LENGTH,
        },
        "questions": questions,
    }


def export_wizard_answer(question: Question, value: Any) -> dict[str, Any]:
    """Shape a single wizard submission for schema documentation / client validators."""
    payload: dict[str, Any] = {
        "question_order": question.order,
        "question_type": QUESTION_TYPE_SCHEMA_MAP[question.type],
    }
    if question.type in {Question.Type.SINGLE_CHOICE, Question.Type.MULTIPLE_CHOICE}:
        if question.type == Question.Type.MULTIPLE_CHOICE:
            payload["choice_ids"] = [choice.pk for choice in value] if value else []
        elif value is not None:
            payload["choice_id"] = value.pk
    elif question.type in {Question.Type.SHORT_TEXT, Question.Type.LONG_TEXT}:
        payload["text"] = value or ""
    elif question.type == Question.Type.NUMBER:
        payload["number"] = str(value) if value is not None else None
    elif question.type == Question.Type.DATE:
        payload["date"] = value.isoformat() if value else None
    elif question.type == Question.Type.RATING and value is not None:
        payload["choice_id"] = value.pk
    return payload


def load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_json(instance: dict[str, Any], schema_path: Path) -> list[str]:
    """Return validation error messages, or [] if valid / jsonschema not installed."""
    try:
        import jsonschema
    except ImportError:
        return []

    validator = jsonschema.Draft202012Validator(load_schema(schema_path))
    errors = sorted(validator.iter_errors(instance), key=lambda exc: exc.path)
    return [exc.message for exc in errors]

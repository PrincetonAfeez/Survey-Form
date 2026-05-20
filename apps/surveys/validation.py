"""Single source of truth for survey domain validation.

All layers call into this module:
- Model ``clean()`` / ``save()`` → ``validate_*`` then ``raise ValidationError``
- Wizard forms → ``validate_answer_value()`` (same rules as ``Answer``)
- Admin mixin → model ``full_clean()`` (no duplicate rules)
- JSON Schema export → ``export_survey_definition()`` in ``schema_contract.py``

See ``docs/validation.md`` for the end-to-end flow.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError

from .constants import LONG_TEXT_MAX_LENGTH, SHORT_TEXT_MAX_LENGTH

if TYPE_CHECKING:
    from .models import Answer, Question, Survey


def validate_survey(survey: Survey) -> dict[str, list[str]]:  # noqa: F821
    """Return field errors for survey publish rules (empty dict if valid)."""
    errors: dict[str, list[str]] = {}
    if not survey.is_published or not survey.pk:
        return errors
    questions = survey.questions.prefetch_related("choices")
    if not questions.exists():
        errors.setdefault("is_published", []).append(
            "Published surveys must have at least one question."
        )
        return errors
    for question in questions:
        if question.accepts_choices and not question.choices.exists():
            errors.setdefault("is_published", []).append(
                f'Question "{question.text[:50]}" ({question.get_type_display()}) '
                "requires at least one choice before publishing."
            )
            break
    return errors


def validate_survey_after_save(survey: Survey) -> dict[str, list[str]]:
    """Re-check publish rules once the survey row exists (closes ORM create gaps)."""
    if not survey.is_published or not survey.pk:
        return {}
    if survey.questions.exists():
        return {}
    return {
        "is_published": ["Published surveys must have at least one question."],
    }


def validate_question(question: Question) -> dict[str, list[str]]:
    from .models import Question

    errors: dict[str, list[str]] = {}
    needs_explicit_choices = (
        question.accepts_choices and question.type not in Question._AUTO_SEEDED_TYPES
    )
    if needs_explicit_choices and question.pk and not question.choices.exists():
        errors.setdefault("type", []).append("This question type requires at least one choice.")
    if question.pk and not question.accepts_choices:
        previous_type = (
            Question.objects.filter(pk=question.pk).values_list("type", flat=True).first()
        )
        if previous_type in question._CHOICE_TYPES and question.answers_reference_choices():
            errors.setdefault("type", []).append(
                "Cannot change type: answers reference existing choices."
            )
    return errors


def validate_answer(
    answer: Answer,
    *,
    choice_count: int | None = None,
    multi_choice_values=None,
    check_required: bool = False,
) -> dict[str, list[str]]:
    """Validate typed answer columns; optional requiredness for wizard/repository writes.

    ``multi_choice_values`` (iterable of ``Choice``) lets the validator also confirm
    each selected choice belongs to the answered question. When provided, it
    supersedes ``choice_count`` for the requiredness count.
    """
    from .models import Question

    errors: dict[str, list[str]] = {}
    question = answer.question
    qtype = question.type
    has_text = bool(answer.text_value)
    has_number = answer.number_value is not None
    has_date = answer.date_value is not None
    has_choice = answer.choice_id is not None
    multi_choice_list = list(multi_choice_values) if multi_choice_values is not None else None
    if multi_choice_list is not None:
        m2m_count = len(multi_choice_list)
    else:
        m2m_count = choice_count if choice_count is not None else 0

    if qtype in {Question.Type.SHORT_TEXT, Question.Type.LONG_TEXT}:
        if has_number or has_date or has_choice:
            errors.setdefault("text_value", []).append(
                "Text answers cannot also store number, date, or choice data."
            )
        if qtype == Question.Type.SHORT_TEXT and answer.text_value:
            if len(answer.text_value) > SHORT_TEXT_MAX_LENGTH:
                errors.setdefault("text_value", []).append(
                    f"Short text answers cannot exceed {SHORT_TEXT_MAX_LENGTH} characters."
                )
        if qtype == Question.Type.LONG_TEXT and answer.text_value:
            if len(answer.text_value) > LONG_TEXT_MAX_LENGTH:
                errors.setdefault("text_value", []).append(
                    f"Long text answers cannot exceed {LONG_TEXT_MAX_LENGTH} characters."
                )
    elif qtype == Question.Type.NUMBER:
        if has_text or has_date or has_choice:
            errors.setdefault("number_value", []).append(
                "Number answers cannot also store text, date, or choice data."
            )
    elif qtype == Question.Type.DATE:
        if has_text or has_number or has_choice:
            errors.setdefault("date_value", []).append(
                "Date answers cannot also store text, number, or choice data."
            )
    elif qtype == Question.Type.RATING:
        if has_text or has_date or has_choice:
            errors.setdefault("number_value", []).append(
                "Rating answers are stored as a number only."
            )
    elif qtype in {Question.Type.SINGLE_CHOICE, Question.Type.LIKERT}:
        if has_text or has_number or has_date:
            errors.setdefault("choice", []).append(
                "Choice answers cannot also store text, number, or date data."
            )
        if answer.choice_id and answer.choice.question_id != answer.question_id:
            errors.setdefault("choice", []).append(
                "Selected choice must belong to the answered question."
            )
    elif qtype == Question.Type.MULTIPLE_CHOICE:
        if has_text or has_number or has_date or has_choice:
            errors.setdefault("choices", []).append(
                "Multiple-choice answers are stored only in the choices relation."
            )
        if multi_choice_list and answer.question_id:
            for choice in multi_choice_list:
                if getattr(choice, "question_id", None) != answer.question_id:
                    errors.setdefault("choices", []).append(
                        "Selected choices must belong to the answered question."
                    )
                    break

    if (
        answer.response_id
        and answer.question_id
        and answer.response.survey_id != answer.question.survey_id
    ):
        errors.setdefault("question", []).append(
            "The answer question must belong to the response survey."
        )

    if check_required and question.is_required:
        _append_required_errors(errors, qtype, answer, m2m_count)

    return errors


def validate_answer_value(question: Question, value: Any) -> str | None:
    """
    Wizard-layer check: same rules as ``Answer`` for a single submitted ``value``.

    Returns the first error message for the ``value`` field, or ``None`` if valid.
    """
    from .models import Answer, Question

    answer = Answer(question=question, response_id=0)
    _apply_value_to_answer(answer, question, value)
    if question.type == Question.Type.MULTIPLE_CHOICE:
        mc_values = list(value) if value else []
        errors = validate_answer(answer, multi_choice_values=mc_values, check_required=True)
    else:
        errors = validate_answer(answer, check_required=True)
    if not errors:
        return None
    first_field = next(iter(errors))
    return errors[first_field][0]


def raise_validation_error(errors: dict[str, list[str]]) -> None:
    if errors:
        raise ValidationError({field: msgs for field, msgs in errors.items()})


def _append_required_errors(
    errors: dict[str, list[str]],
    qtype: str,
    answer: Answer,
    m2m_count: int,
) -> None:
    from .models import Question

    if qtype in {Question.Type.SHORT_TEXT, Question.Type.LONG_TEXT}:
        if not answer.text_value:
            errors.setdefault("text_value", []).append("This field is required.")
    elif qtype == Question.Type.NUMBER:
        if answer.number_value is None:
            errors.setdefault("number_value", []).append("This field is required.")
    elif qtype == Question.Type.DATE:
        if answer.date_value is None:
            errors.setdefault("date_value", []).append("This field is required.")
    elif qtype in {Question.Type.SINGLE_CHOICE, Question.Type.LIKERT}:
        if not answer.choice_id:
            errors.setdefault("value", []).append("This field is required.")
    elif qtype == Question.Type.RATING:
        if answer.number_value is None:
            errors.setdefault("value", []).append("This field is required.")
    elif qtype == Question.Type.MULTIPLE_CHOICE and m2m_count == 0:
        errors.setdefault("value", []).append("This field is required.")


def _apply_value_to_answer(answer: Answer, question: Question, value: Any) -> None:
    from .models import Question

    answer.text_value = ""
    answer.number_value = None
    answer.date_value = None
    answer.choice = None

    if question.type in {Question.Type.SHORT_TEXT, Question.Type.LONG_TEXT}:
        answer.text_value = value or ""
    elif question.type == Question.Type.NUMBER:
        answer.number_value = value
    elif question.type == Question.Type.DATE:
        answer.date_value = value if isinstance(value, date) else None
    elif question.type in {Question.Type.SINGLE_CHOICE, Question.Type.LIKERT}:
        answer.choice = value
    elif question.type == Question.Type.RATING:
        from .lib import rating_value

        answer.number_value = rating_value(value) if value else None
    elif question.type == Question.Type.MULTIPLE_CHOICE:
        pass

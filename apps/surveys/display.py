from __future__ import annotations

from decimal import Decimal

from .models import Answer, Question


def trim_decimal(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, Decimal):
        value = value.normalize()
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    return str(value)


def format_answer_value(answer: Answer | None) -> str:
    if answer is None:
        return ""
    qtype = answer.question.type
    if qtype in {Question.Type.SHORT_TEXT, Question.Type.LONG_TEXT}:
        return answer.text_value
    if qtype in {Question.Type.NUMBER, Question.Type.RATING}:
        if answer.number_value is None:
            return ""
        return trim_decimal(answer.number_value)
    if qtype == Question.Type.DATE:
        return answer.date_value.isoformat() if answer.date_value else ""
    if qtype in {Question.Type.SINGLE_CHOICE, Question.Type.LIKERT}:
        return answer.choice.label if answer.choice else ""
    if qtype == Question.Type.MULTIPLE_CHOICE:
        return "; ".join(choice.label for choice in answer.choices.all())
    return ""

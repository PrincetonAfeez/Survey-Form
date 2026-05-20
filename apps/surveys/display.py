"""Display functions for surveys app"""

from __future__ import annotations

from .lib import trim_decimal
from .models import Answer, Question


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

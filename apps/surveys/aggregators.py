"""Aggregators for surveys app"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from statistics import median

from django.db.models import Count
from django.db.models.functions import TruncWeek

from .models import Answer, Question, Response, Survey


def aggregate_survey(survey: Survey) -> list[dict]:
    return [
        aggregate_question(question) for question in survey.questions.prefetch_related("choices")
    ]


def aggregate_question(question: Question) -> dict:
    if question.type in {Question.Type.SINGLE_CHOICE, Question.Type.LIKERT}:
        return aggregate_choice(question)
    if question.type == Question.Type.MULTIPLE_CHOICE:
        return aggregate_multiple_choice(question)
    if question.type == Question.Type.RATING:
        return aggregate_number(question, rating=True)
    if question.type == Question.Type.NUMBER:
        return aggregate_number(question)
    if question.type in {Question.Type.SHORT_TEXT, Question.Type.LONG_TEXT}:
        return aggregate_text(question)
    if question.type == Question.Type.DATE:
        return aggregate_date(question)
    raise ValueError(f"Unsupported question type: {question.type}")


def _answers_for_completed_question(question: Question):
    return Answer.objects.for_completed_question(question)


def aggregate_choice(question: Question) -> dict:
    answer_counts = Counter(
        _answers_for_completed_question(question)
        .filter(choice__isnull=False)
        .values_list("choice_id", flat=True)
    )
    rows = [
        {"label": choice.label, "count": answer_counts.get(choice.id, 0)}
        for choice in question.choices.all()
    ]
    total = sum(row["count"] for row in rows)
    return {"question": question, "kind": "choice", "rows": rows, "total": total}


def aggregate_multiple_choice(question: Question) -> dict:
    through = Answer.choices.through
    counts = Counter(
        through.objects.filter(
            answer__question=question,
            answer__response__completed_at__isnull=False,
        ).values_list("choice_id", flat=True)
    )
    rows = [
        {"label": choice.label, "count": counts.get(choice.id, 0)}
        for choice in question.choices.all()
    ]
    total = _answers_for_completed_question(question).count()
    return {"question": question, "kind": "choice", "rows": rows, "total": total}


def aggregate_number(question: Question, *, rating: bool = False) -> dict:
    values = [
        answer.number_value
        for answer in _answers_for_completed_question(question).exclude(number_value__isnull=True)
    ]
    distribution = Counter(values)
    if values:
        mean_value = sum(values, Decimal("0")) / Decimal(len(values))
        minimum = min(values)
        maximum = max(values)
        median_value = median(values)
    else:
        mean_value = minimum = maximum = median_value = None

    if rating:
        scale = [Decimal(i) for i in range(1, 6)]
        rows = [{"label": str(value), "count": distribution.get(value, 0)} for value in scale]
    else:
        rows = [
            {"label": str(value), "count": distribution.get(value, 0)}
            for value in sorted(distribution.keys())
        ]

    return {
        "question": question,
        "kind": "number",
        "values": values,
        "rows": rows,
        "count": len(values),
        "min": minimum,
        "max": maximum,
        "mean": mean_value,
        "median": median_value,
    }


def aggregate_text(question: Question) -> dict:
    base = _answers_for_completed_question(question).exclude(text_value="")
    answers = base.select_related("response").order_by("-updated_at")[:25]
    return {
        "question": question,
        "kind": "text",
        "answers": answers,
        "count": base.count(),
    }


def aggregate_date(question: Question) -> dict:
    rows = (
        _answers_for_completed_question(question)
        .exclude(date_value__isnull=True)
        .annotate(week=TruncWeek("date_value"))
        .values("week")
        .annotate(count=Count("id"))
        .order_by("week")
    )
    return {"question": question, "kind": "date", "rows": list(rows)}


def response_metrics(survey: Survey) -> dict:
    responses = Response.objects.for_survey(survey)
    started = responses.count()
    complete = responses.complete().count()
    durations = [
        response.completion_seconds
        for response in responses.complete()
        if response.completion_seconds is not None
    ]
    return {
        "started": started,
        "complete": complete,
        "completion_rate": (complete / started * 100) if started else 0,
        "median_completion_seconds": median(durations) if durations else None,
    }

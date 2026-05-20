from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.db import transaction
from django.db.models import Q, QuerySet

from .models import Answer, BranchRule, Choice, Question, Response, Survey


class SurveyRepository:
    @staticmethod
    def get_published() -> QuerySet[Survey]:
        return Survey.objects.published()

    @staticmethod
    def get_by_slug(slug: str) -> Survey | None:
        return Survey.objects.published().filter(slug=slug).first()

    @staticmethod
    def get_for_preview(survey_id: int | str, user) -> Survey | None:
        if not getattr(user, "is_staff", False):
            return None
        lookup = {"slug": survey_id} if isinstance(survey_id, str) else {"id": survey_id}
        return Survey.objects.filter(**lookup).first()

    @staticmethod
    def get_for_results(survey_id: int, user) -> Survey | None:
        if not getattr(user, "is_staff", False):
            return None
        return Survey.objects.filter(id=survey_id).first()

    @staticmethod
    def questions_for_survey(survey: Survey) -> QuerySet[Question]:
        return survey.questions.prefetch_related("choices")

    @staticmethod
    def get_question_by_order(survey: Survey, order: int) -> Question | None:
        return survey.questions.prefetch_related("choices").filter(order=order).first()

    @staticmethod
    def get_next_question_by_order(survey: Survey, order: int) -> Question | None:
        return survey.questions.filter(order__gt=order).order_by("order").first()

    @staticmethod
    def first_question_order(survey: Survey) -> int | None:
        return survey.questions.order_by("order").values_list("order", flat=True).first()

    @staticmethod
    def get_branch_target(question: Question, choice: Choice | None) -> Question | None:
        if choice is None:
            return None
        rule = (
            BranchRule.objects.select_related("next_question")
            .filter(question=question, choice=choice)
            .first()
        )
        return rule.next_question if rule else None


class ResponseRepository:
    @staticmethod
    def for_respondent(uuid: UUID | str) -> Response | None:
        return Response.objects.select_related("survey").filter(uuid=uuid).first()

    @staticmethod
    def start(survey: Survey) -> Response:
        first_order = SurveyRepository.first_question_order(survey)
        if first_order is None:
            raise ValueError("Cannot start a survey with no questions.")
        return Response.objects.create(survey=survey, current_step=first_order)

    @staticmethod
    def answer_for(response: Response, question: Question) -> Answer | None:
        return (
            response.answers.select_related("choice", "question")
            .prefetch_related("choices")
            .filter(question=question)
            .first()
        )

    @staticmethod
    @transaction.atomic
    def save_answer(response: Response, question: Question, payload: dict) -> Answer:
        answer, _ = Answer.objects.select_for_update().get_or_create(
            response=response, question=question
        )
        value = payload.get("value")

        answer.text_value = ""
        answer.number_value = None
        answer.date_value = None
        answer.choice = None
        answer.save()
        answer.choices.clear()

        if question.type in {Question.Type.SHORT_TEXT, Question.Type.LONG_TEXT}:
            answer.text_value = value or ""
        elif question.type == Question.Type.NUMBER:
            answer.number_value = value
        elif question.type == Question.Type.DATE:
            answer.date_value = value
        elif question.type in {Question.Type.SINGLE_CHOICE, Question.Type.LIKERT}:
            answer.choice = value
        elif question.type == Question.Type.MULTIPLE_CHOICE:
            answer.save()
            answer.choices.set(value)
            return answer
        elif question.type == Question.Type.RATING:
            answer.number_value = rating_value(value)

        answer.save()
        return answer

    @staticmethod
    def move_to_step(response: Response, step: int) -> Response:
        response.current_step = step
        response.save(update_fields=["current_step"])
        return response

    @staticmethod
    def complete(response: Response) -> Response:
        response.mark_complete()
        response.save(update_fields=["completed_at"])
        return response

    @staticmethod
    def filter_by_answer_query(queryset, query: str):
        text = query.strip()
        if not text:
            return queryset
        filters = (
            Q(answers__text_value__icontains=text)
            | Q(answers__choice__label__icontains=text)
            | Q(answers__choices__label__icontains=text)
        )
        try:
            filters |= Q(answers__date_value=date.fromisoformat(text))
        except ValueError:
            pass
        try:
            filters |= Q(answers__number_value=Decimal(text))
        except InvalidOperation:
            pass
        return queryset.filter(filters).distinct()

    @staticmethod
    def prune_answers_off_path(response: Response, path: list[int]) -> int:
        """Delete answers for questions not on the session path (e.g. after re-branching)."""
        if not path:
            return 0
        on_path = Question.objects.filter(survey_id=response.survey_id, order__in=path)
        deleted, _ = (
            Answer.objects.filter(response=response)
            .exclude(question__in=on_path)
            .delete()
        )
        return deleted

    @staticmethod
    def list_for_survey(survey: Survey, *, complete_only: bool = False):
        queryset = (
            Response.objects.for_survey(survey)
            .prefetch_related("answers__choices", "answers__choice", "answers__question")
            .order_by("-started_at")
        )
        return queryset.complete() if complete_only else queryset


def rating_value(value: Choice | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value.label)
    except (InvalidOperation, TypeError):
        return Decimal(value.order)

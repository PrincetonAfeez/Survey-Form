"""Repositories for surveys app"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.db import transaction
from django.db.models import Q, QuerySet

from .lib import rating_value
from .models import Answer, BranchRule, Choice, Question, Response, Survey
from .validation import raise_validation_error, validate_answer


class SurveyRepository:
    @staticmethod
    def get_published() -> QuerySet[Survey]:
        return Survey.objects.published()

    @staticmethod
    def get_by_slug(slug: str) -> Survey | None:
        return Survey.objects.published().filter(slug=slug).first()

    @staticmethod
    def get_by_slug_any(slug: str) -> Survey | None:
        return Survey.objects.filter(slug=slug).first()

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
    def get_question_by_id(survey: Survey, question_id: int) -> Question | None:
        return survey.questions.prefetch_related("choices").filter(pk=question_id).first()

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
    def is_resume_allowed(response: Response, session_uuid: str | None) -> bool:
        """
        Reject resume when this browser session already started a newer draft.

        Unrelated respondents (empty or different session) may still use their tokens.
        """
        if not session_uuid:
            return True
        try:
            session_id = UUID(str(session_uuid))
        except (ValueError, TypeError):
            return True
        if session_id == response.uuid:
            return True
        session_response = ResponseRepository.for_respondent(session_id)
        if session_response is None or session_response.survey_id != response.survey_id:
            return True
        return session_response.started_at <= response.started_at

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

        # Snapshot is for display/audit; the column caps at 500 chars (full text
        # remains on Question.text), so truncate rather than reject long prompts.
        answer.question_text_snapshot = question.text[:500]

        if question.type in {Question.Type.SHORT_TEXT, Question.Type.LONG_TEXT}:
            answer.text_value = value or ""
        elif question.type == Question.Type.NUMBER:
            answer.number_value = value
        elif question.type == Question.Type.DATE:
            answer.date_value = value
        elif question.type in {Question.Type.SINGLE_CHOICE, Question.Type.LIKERT}:
            answer.choice = value
        elif question.type == Question.Type.RATING:
            answer.number_value = rating_value(value)

        multi_choice_values = (
            list(value or []) if question.type == Question.Type.MULTIPLE_CHOICE else None
        )
        raise_validation_error(
            validate_answer(
                answer,
                multi_choice_values=multi_choice_values,
                check_required=True,
            )
        )

        answer.save()

        if question.type == Question.Type.MULTIPLE_CHOICE:
            answer.choices.set(value or [])
        else:
            answer.choices.clear()

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
    def sync_current_step(survey: Survey, response: Response) -> int:
        """
        Ensure current_step points at an existing question; repair after admin edits.
        Returns the order to use for redirects.
        """
        if SurveyRepository.get_question_by_order(survey, response.current_step):
            return response.current_step

        answered = response.answers.select_related("question").order_by("question__order").last()
        if answered:
            following = SurveyRepository.get_next_question_by_order(survey, answered.question.order)
            step = following.order if following else answered.question.order
        else:
            step = SurveyRepository.first_question_order(survey)
            if step is None:
                raise ValueError("Survey has no questions.")

        ResponseRepository.move_to_step(response, step)
        return step

    @staticmethod
    def filter_by_answer_query(queryset, query: str):
        text = query.strip()
        if not text:
            return queryset
        filters = (
            Q(answers__text_value__icontains=text)
            | Q(answers__question_text_snapshot__icontains=text)
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
    def prune_answers_off_path(response: Response, path_question_ids: list[int]) -> int:
        """Delete answers for questions not on the session path (e.g. after re-branching)."""
        if not path_question_ids:
            return 0
        on_path = Question.objects.filter(survey_id=response.survey_id, pk__in=path_question_ids)
        deleted, _ = Answer.objects.filter(response=response).exclude(question__in=on_path).delete()
        return deleted

    @staticmethod
    def list_for_survey(survey: Survey, *, complete_only: bool = False):
        queryset = (
            Response.objects.for_survey(survey)
            .prefetch_related("answers__choices", "answers__choice", "answers__question")
            .order_by("-started_at")
        )
        return queryset.complete() if complete_only else queryset

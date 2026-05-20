"""Branching navigation helpers (no SurveyRunner dependency)"""

from __future__ import annotations

from .models import Choice, Question, Response, Survey
from .repositories import ResponseRepository, SurveyRepository


def next_question(
    survey: Survey, question: Question, answered_choice: Choice | None
) -> Question | None:
    branch_target = None
    if question.type == Question.Type.SINGLE_CHOICE:
        branch_target = SurveyRepository.get_branch_target(question, answered_choice)
    return branch_target or SurveyRepository.get_next_question_by_order(survey, question.order)


def choice_from_saved_response(response: Response, question: Question) -> Choice | None:
    if not response.pk:
        return None
    answer = ResponseRepository.answer_for(response, question)
    if answer is None or question.type != Question.Type.SINGLE_CHOICE:
        return None
    return answer.choice

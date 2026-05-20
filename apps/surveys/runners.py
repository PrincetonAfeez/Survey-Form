"""SurveyRunner for surveys app"""

from __future__ import annotations

from dataclasses import dataclass

from django import forms
from django.db import transaction

from .forms import form_for_question
from .models import Choice, Question, Response, Survey
from .navigation import choice_from_saved_response
from .navigation import next_question as navigate_next
from .pathing import walk_path_from_response
from .repositories import ResponseRepository, SurveyRepository


@dataclass(frozen=True)
class SubmitResult:
    ok: bool
    form: forms.Form
    question: Question
    next_question: Question | None = None
    is_final: bool = False

    @property
    def errors(self):
        return self.form.errors

    @property
    def next_step(self) -> int | None:
        return self.next_question.order if self.next_question else None


class SurveyRunner:
    def __init__(self, survey: Survey, response: Response, *, record: bool = True):
        self.survey = survey
        self.response = response
        self.record = record

    def current_question(self) -> Question | None:
        return self.question_for_step(self.response.current_step)

    def question_for_step(self, step: int) -> Question | None:
        return SurveyRepository.get_question_by_order(self.survey, step)

    def step_number(self) -> int:
        return self.response.current_step

    def total_questions(self) -> int:
        return SurveyRepository.questions_for_survey(self.survey).count()

    def position_for_step(self, step: int) -> int:
        """1-indexed ordinal position of the question at `step` (order) in the survey."""
        position = self.survey.questions.filter(order__lte=step).count()
        return max(1, position)

    def progress_percent(self, step: int) -> int:
        """
        Approximate progress for the bar (ADR-0006 keeps the label as ~total).

        Uses ordinal position in the survey's question list — not the raw `order` —
        so non-1,2,3 orders (e.g. 10/20/30) still render 0-100 correctly.
        Biases upward when branching skips questions so the bar does not stall.
        """
        total = self.total_questions()
        if total <= 0:
            return 0
        if not self.survey.questions.filter(order__gt=step).exists():
            return 100

        position = self.position_for_step(step)
        if self.record and self.response.pk:
            answered = self.response.answers.count()
        else:
            answered = max(0, position - 1)

        by_position = min(100, int(position / total * 100))
        gap = position - answered - 1
        if gap > 0:
            walked = answered + 1
            by_path = min(100, int(walked / (walked + 1) * 100))
            return max(by_position, by_path, 75 if answered >= 1 else by_position)

        return min(99, by_position)

    def form_for(self, question: Question, *, data=None):
        instance = None
        if self.record and self.response.pk:
            instance = ResponseRepository.answer_for(self.response, question)
        return form_for_question(question, data=data, instance=instance)

    @transaction.atomic
    def submit(self, payload: dict, *, step: int | None = None) -> SubmitResult:
        question = self.question_for_step(step or self.step_number())
        if question is None:
            raise ValueError("Cannot submit a missing question.")

        form = self.form_for(question, data=payload)
        if not form.is_valid():
            return SubmitResult(ok=False, form=form, question=question)

        answered_choice = self._branch_choice(question, form.cleaned_data)
        if self.record:
            ResponseRepository.save_answer(self.response, question, form.cleaned_data)

        next_question = self.next_question(question, answered_choice)
        if self.record:
            if next_question:
                ResponseRepository.move_to_step(self.response, next_question.order)
            else:
                ResponseRepository.complete(self.response)
                self._discard_off_route_answers()

        return SubmitResult(
            ok=True,
            form=form,
            question=question,
            next_question=next_question,
            is_final=next_question is None,
        )

    def next_question(self, question: Question, answered_choice: Choice | None) -> Question | None:
        return navigate_next(self.survey, question, answered_choice)

    def is_complete(self) -> bool:
        return self.response.is_complete

    def has_next_step(self, question: Question) -> bool:
        return self.next_question(question, self.choice_from_saved_answer(question)) is not None

    def is_final_step(self, question: Question) -> bool:
        return not self.has_next_step(question)

    def choice_from_saved_answer(self, question: Question) -> Choice | None:
        if not self.record:
            return None
        return choice_from_saved_response(self.response, question)

    def _discard_off_route_answers(self) -> None:
        """After completion, drop saved answers for questions the final route skipped."""
        route = walk_path_from_response(self.survey, self.response)
        ResponseRepository.prune_answers_off_path(self.response, route)

    @staticmethod
    def _branch_choice(question: Question, cleaned_data: dict) -> Choice | None:
        if question.type != Question.Type.SINGLE_CHOICE:
            return None
        value = cleaned_data.get("value")
        return value if isinstance(value, Choice) else None

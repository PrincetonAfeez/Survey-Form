"""Session path reconstruction and branch-cycle detection."""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count

from .models import BranchRule, Question, Response, Survey
from .navigation import choice_from_saved_response, next_question
from .repositories import SurveyRepository


def build_path_from_response(survey: Survey, response: Response) -> list[int]:
    """
    Reconstruct the question-order path from saved answers and branching rules.

    Stops at current_step, on a branch cycle, or after at most question_count steps.
    """
    first_order = SurveyRepository.first_question_order(survey)
    if first_order is None:
        return []

    question = SurveyRepository.get_question_by_order(survey, first_order)
    path: list[int] = []
    visited: set[int] = set()
    limit = survey.questions.count() + 1

    while question is not None and len(path) < limit:
        order = question.order
        if order in visited:
            break
        visited.add(order)
        path.append(order)
        if order == response.current_step:
            return path
        choice = choice_from_saved_response(response, question)
        question = next_question(survey, question, choice)
    return path


def branch_rule_creates_cycle(rule: BranchRule) -> bool:
    """
    True if the survey's navigation graph would contain a cycle once this rule applies.

    The graph carries every possible "next question" edge: explicit BranchRule
    targets, plus the implicit next-by-order fallback wherever a respondent can
    still reach it (a non-single-choice question, or a single-choice question with
    at least one choice that has no branch rule).
    """
    if not rule.question_id or not rule.next_question_id:
        return False

    survey_id = rule.question.survey_id
    questions = list(
        Question.objects.filter(survey_id=survey_id)
        .annotate(choice_total=Count("choices"))
        .order_by("order")
    )
    next_by_order: dict[int, int | None] = {}
    for index, question in enumerate(questions):
        following = questions[index + 1] if index + 1 < len(questions) else None
        next_by_order[question.id] = following.id if following else None

    saved_rules = BranchRule.objects.filter(question__survey_id=survey_id)
    if rule.pk:
        saved_rules = saved_rules.exclude(pk=rule.pk)
    branch_targets: dict[int, set[int]] = defaultdict(set)
    ruled_choices: dict[int, set[int]] = defaultdict(set)
    for candidate in [*saved_rules, rule]:
        branch_targets[candidate.question_id].add(candidate.next_question_id)
        if candidate.choice_id:
            ruled_choices[candidate.question_id].add(candidate.choice_id)

    adjacency: dict[int, set[int]] = defaultdict(set)
    for question in questions:
        edges = set(branch_targets.get(question.id, ()))
        every_choice_branches = (
            question.type == Question.Type.SINGLE_CHOICE
            and question.choice_total > 0
            and len(ruled_choices.get(question.id, ())) >= question.choice_total
        )
        fallback = next_by_order.get(question.id)
        if fallback is not None and not every_choice_branches:
            edges.add(fallback)
        adjacency[question.id] = edges

    visited: set[int] = set()
    on_stack: set[int] = set()

    def reaches_cycle(node: int) -> bool:
        visited.add(node)
        on_stack.add(node)
        for target in adjacency.get(node, ()):
            if target in on_stack:
                return True
            if target not in visited and reaches_cycle(target):
                return True
        on_stack.discard(node)
        return False

    return any(
        reaches_cycle(question.id) for question in questions if question.id not in visited
    )

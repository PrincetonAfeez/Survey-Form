"""Session path reconstruction and branch-cycle detection"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count

from .models import BranchRule, Question, Response, Survey
from .navigation import choice_from_saved_response, next_question
from .repositories import SurveyRepository


def answered_question_ids(response: Response) -> list[int]:
    """Question primary keys with saved answers, in survey order."""
    seen: set[int] = set()
    ordered: list[int] = []
    for question_id in response.answers.order_by("question__order").values_list(
        "question_id", flat=True
    ):
        if question_id not in seen:
            seen.add(question_id)
            ordered.append(question_id)
    return ordered


def merge_path_with_answered(path_ids: list[int], response: Response) -> list[int]:
    """Keep answered questions in path even if admin reordering breaks the walk."""
    merged: list[int] = []
    for question_id in answered_question_ids(response):
        if question_id not in merged:
            merged.append(question_id)
    for question_id in path_ids:
        if question_id not in merged:
            merged.append(question_id)
    return merged


def walk_path_from_response(survey: Survey, response: Response) -> list[int]:
    """Branch-following path of question ids (no merge with orphan answers)."""
    first_order = SurveyRepository.first_question_order(survey)
    if first_order is None:
        return []

    question = SurveyRepository.get_question_by_order(survey, first_order)
    path: list[int] = []
    visited: set[int] = set()
    limit = survey.questions.count() + 1

    while question is not None and len(path) < limit:
        question_id = question.id
        if question_id in visited:
            break
        visited.add(question_id)
        path.append(question_id)
        if question.order == response.current_step:
            return path
        choice = choice_from_saved_response(response, question)
        question = next_question(survey, question, choice)
    return path


def build_path_from_response(survey: Survey, response: Response) -> list[int]:
    """
    Reconstruct the session path from saved answers and branching rules.

    Merges in any answered question ids so reordering does not drop saved answers.
    """
    return merge_path_with_answered(walk_path_from_response(survey, response), response)


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

    return any(reaches_cycle(question.id) for question in questions if question.id not in visited)

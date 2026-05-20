""" Path rebuild, answer pruning, and branch-cycle validation tests """

import pytest
from apps.surveys.models import BranchRule, Choice, Question, Survey
from apps.surveys.pathing import build_path_from_response
from apps.surveys.repositories import ResponseRepository
from django.core.exceptions import ValidationError
from django.urls import reverse


@pytest.mark.django_db
def test_branch_rule_clean_rejects_two_question_cycle():
    survey = Survey.objects.create(title="Cycle", slug="cycle-branch", is_published=False)
    q1 = Question.objects.create(
        survey=survey, order=1, text="Q1", type=Question.Type.SINGLE_CHOICE
    )
    q2 = Question.objects.create(
        survey=survey, order=2, text="Q2", type=Question.Type.SINGLE_CHOICE
    )
    a = Choice.objects.create(question=q1, order=1, label="A")
    b = Choice.objects.create(question=q2, order=1, label="B")
    BranchRule.objects.create(question=q1, choice=a, next_question=q2)
    rule = BranchRule(question=q2, choice=b, next_question=q1)
    with pytest.raises(ValidationError) as exc:
        rule.full_clean()
    assert "cycle" in str(exc.value).lower()


@pytest.mark.django_db
def test_build_path_terminates_when_branch_cycle_exists_in_db():
    survey = Survey.objects.create(title="Cycle", slug="cycle-path", is_published=False)
    q1 = Question.objects.create(
        survey=survey, order=1, text="Q1", type=Question.Type.SINGLE_CHOICE
    )
    q3 = Question.objects.create(
        survey=survey, order=3, text="Q3", type=Question.Type.SINGLE_CHOICE
    )
    to_q3 = Choice.objects.create(question=q1, order=1, label="Go Q3")
    to_q1 = Choice.objects.create(question=q3, order=1, label="Go Q1")
    BranchRule.objects.create(question=q1, choice=to_q3, next_question=q3)
    BranchRule.objects.bulk_create([BranchRule(question=q3, choice=to_q1, next_question=q1)])
    survey.is_published = True
    survey.save()

    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": to_q3})
    ResponseRepository.save_answer(response, q3, {"value": to_q1})
    response.current_step = 99
    response.save(update_fields=["current_step"])

    path = build_path_from_response(survey, response)
    assert path == [q1.id, q3.id]
    assert len(path) <= survey.questions.count()


@pytest.mark.django_db
def test_step_back_keeps_answers_for_later_steps(client, branching_survey):
    survey, q1, q2, q3, _remote = branching_survey
    office = q1.choices.get(label="Office")
    client.post(reverse("surveys:start", args=[survey.slug]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": office.id})
    client.post(reverse("surveys:step", args=[survey.slug, q2.order]), {"value": "20"})

    # Reviewing earlier steps must not discard answers already given.
    client.get(reverse("surveys:step_back", args=[survey.slug, q3.order]))
    client.get(reverse("surveys:step_back", args=[survey.slug, q2.order]))

    response = survey.responses.get()
    assert response.answers.filter(question=q1).exists()
    assert response.answers.filter(question=q2).exists()


@pytest.mark.django_db
def test_rebranch_prunes_skipped_answers_on_completion(client, branching_survey):
    survey, q1, q2, q3, remote = branching_survey
    office = q1.choices.get(label="Office")
    client.post(reverse("surveys:start", args=[survey.slug]))

    # Walk the office route q1 -> q2 -> q3, then step back to q1.
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": office.id})
    client.post(reverse("surveys:step", args=[survey.slug, q2.order]), {"value": "20"})
    client.get(reverse("surveys:step_back", args=[survey.slug, q3.order]))
    client.get(reverse("surveys:step_back", args=[survey.slug, q2.order]))

    # Re-answer q1 so the branch skips q2; the q2 draft survives until completion.
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": remote.id})
    response = survey.responses.get()
    assert response.answers.filter(question=q2).exists()

    # Completing the remote route prunes the now-skipped q2 answer.
    client.post(
        reverse("surveys:step", args=[survey.slug, q3.order]),
        {"value": q3.choices.get(label="5").id},
    )
    response.refresh_from_db()
    assert response.is_complete
    assert not response.answers.filter(question=q2).exists()
    assert response.answers.filter(question=q1).exists()
    assert response.answers.filter(question=q3).exists()


@pytest.mark.django_db
def test_branch_rule_clean_rejects_cycle_through_order_fallback():
    survey = Survey.objects.create(title="Mixed cycle", slug="mixed-cycle")
    q1 = Question.objects.create(
        survey=survey, order=1, text="Q1", type=Question.Type.SINGLE_CHOICE
    )
    q2 = Question.objects.create(
        survey=survey, order=2, text="Q2", type=Question.Type.SINGLE_CHOICE
    )
    Choice.objects.create(question=q1, order=1, label="A")
    pick = Choice.objects.create(question=q2, order=1, label="B")

    # q1 falls through to q2 by order; a q2 -> q1 branch closes the loop.
    rule = BranchRule(question=q2, choice=pick, next_question=q1)
    with pytest.raises(ValidationError) as exc:
        rule.full_clean()
    assert "cycle" in str(exc.value).lower()


@pytest.mark.django_db
def test_prune_answers_off_path_repository(branching_survey):
    survey, q1, q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": remote})
    ResponseRepository.save_answer(response, q3, {"value": q3.choices.get(label="4")})
    deleted = ResponseRepository.prune_answers_off_path(response, [q1.id])
    assert deleted == 1
    assert response.answers.count() == 1

from datetime import date
from decimal import Decimal

import pytest
from apps.surveys.models import BranchRule, Choice, Question, Survey
from apps.surveys.repositories import ResponseRepository, SurveyRepository, rating_value
from django.core.exceptions import ValidationError


@pytest.mark.django_db
def test_survey_repository_published_and_slug(branching_survey, unpublished_survey):
    survey, *_ = branching_survey
    assert SurveyRepository.get_published().filter(pk=survey.pk).exists()
    assert SurveyRepository.get_by_slug("branching") == survey
    assert SurveyRepository.get_by_slug("draft") is None
    assert SurveyRepository.get_by_slug("missing") is None


@pytest.mark.django_db
def test_survey_repository_preview_and_results(staff_user, regular_user, branching_survey):
    survey, *_ = branching_survey
    assert SurveyRepository.get_for_preview(survey.slug, staff_user) == survey
    assert SurveyRepository.get_for_preview(survey.id, staff_user) == survey
    assert SurveyRepository.get_for_preview(survey.slug, regular_user) is None
    assert SurveyRepository.get_for_results(survey.id, staff_user) == survey
    assert SurveyRepository.get_for_results(survey.id, regular_user) is None


@pytest.mark.django_db
def test_survey_repository_questions_and_branching(branching_survey):
    survey, q1, q2, q3, remote = branching_survey
    assert SurveyRepository.questions_for_survey(survey).count() == 3
    assert SurveyRepository.get_question_by_order(survey, 1) == q1
    assert SurveyRepository.get_question_by_order(survey, 99) is None
    assert SurveyRepository.get_next_question_by_order(survey, 1) == q2
    assert SurveyRepository.get_branch_target(q1, remote) == q3
    assert SurveyRepository.get_branch_target(q1, None) is None
    office = q1.choices.get(label="Office")
    assert SurveyRepository.get_branch_target(q1, office) is None


@pytest.mark.django_db
def test_response_repository_lifecycle(branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    assert response.current_step == 1
    assert ResponseRepository.for_respondent(response.uuid) == response
    assert ResponseRepository.for_respondent("00000000-0000-0000-0000-000000000000") is None

    ResponseRepository.save_answer(response, q1, {"value": remote})
    answer = ResponseRepository.answer_for(response, q1)
    assert answer.choice == remote

    ResponseRepository.move_to_step(response, q3.order)
    response.refresh_from_db()
    assert response.current_step == q3.order

    ResponseRepository.complete(response)
    response.refresh_from_db()
    assert response.is_complete


@pytest.mark.django_db
def test_response_repository_list_and_filter(branching_survey):
    survey, q1, _q2, _q3, remote = branching_survey
    draft = ResponseRepository.start(survey)
    ResponseRepository.save_answer(draft, q1, {"value": remote})
    complete = ResponseRepository.start(survey)
    ResponseRepository.complete(complete)

    assert ResponseRepository.list_for_survey(survey).count() == 2
    assert ResponseRepository.list_for_survey(survey, complete_only=True).count() == 1

    matches = ResponseRepository.filter_by_answer_query(
        ResponseRepository.list_for_survey(survey), "Remote"
    )
    assert matches.filter(pk=draft.pk).exists()

    by_date = ResponseRepository.filter_by_answer_query(
        ResponseRepository.list_for_survey(survey), "2099-01-01"
    )
    assert by_date.count() == 0


@pytest.mark.django_db
def test_filter_by_answer_query_number_and_empty(branching_survey):
    survey, _q1, q2, _q3, _remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q2, {"value": Decimal("15")})

    hits = ResponseRepository.filter_by_answer_query(
        ResponseRepository.list_for_survey(survey), "15"
    )
    assert hits.count() == 1
    assert ResponseRepository.filter_by_answer_query(
        ResponseRepository.list_for_survey(survey), ""
    ).count() == 1


@pytest.mark.django_db
def test_save_answer_updates_existing_row(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    ResponseRepository.save_answer(response, full_survey["short"], {"value": "first"})
    ResponseRepository.save_answer(response, full_survey["short"], {"value": "second"})
    assert response.answers.count() == 1
    assert response.answers.get().text_value == "second"


@pytest.mark.django_db
def test_save_answer_date_type(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    answer = ResponseRepository.save_answer(
        response, full_survey["date"], {"value": date(2026, 5, 16)}
    )
    assert answer.date_value == date(2026, 5, 16)


@pytest.mark.django_db
def test_rating_value_from_label_and_order_fallback():
    survey = Survey.objects.create(title="R", slug="r")
    q = Question.objects.create(survey=survey, order=1, text="Rate", type=Question.Type.RATING)
    numeric = Choice.objects.get(question=q, label="4")
    assert rating_value(numeric) == Decimal("4")

    custom = Choice.objects.create(question=q, order=99, label="N/A")
    assert rating_value(custom) == Decimal("99")
    assert rating_value(None) is None


@pytest.mark.django_db
def test_branch_rule_rejects_cross_survey_target(full_survey):
    other = Survey.objects.create(title="Other", slug="other")
    target = Question.objects.create(
        survey=other, order=1, text="Elsewhere", type=Question.Type.SHORT_TEXT
    )
    rule = BranchRule(
        question=full_survey["single"],
        choice=full_survey["single_yes"],
        next_question=target,
    )

    with pytest.raises(ValidationError):
        rule.full_clean()

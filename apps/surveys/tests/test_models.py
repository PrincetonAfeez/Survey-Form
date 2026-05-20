import pytest
from apps.surveys.models import Answer, BranchRule, Choice, Question, Response, Survey
from django.core.exceptions import ValidationError


@pytest.mark.django_db
def test_survey_str():
    survey = Survey.objects.create(title="My Survey", slug="my")
    assert str(survey) == "My Survey"


@pytest.mark.django_db
def test_question_str_and_accepts_choices():
    survey = Survey.objects.create(title="S", slug="s")
    text_q = Question.objects.create(
        survey=survey, order=1, text="Name?", type=Question.Type.SHORT_TEXT
    )
    choice_q = Question.objects.create(
        survey=survey, order=2, text="Pick", type=Question.Type.SINGLE_CHOICE
    )
    assert "Q1" in str(text_q)
    assert text_q.accepts_choices is False
    assert choice_q.accepts_choices is True
    rating_q = Question.objects.create(
        survey=survey, order=3, text="Rate", type=Question.Type.RATING
    )
    assert rating_q.accepts_choices is True


@pytest.mark.django_db
def test_choice_str():
    survey = Survey.objects.create(title="S", slug="s")
    q = Question.objects.create(survey=survey, order=1, text="?", type=Question.Type.RATING)
    choice = Choice.objects.get(question=q, label="3")
    assert str(choice) == "3"


@pytest.mark.django_db
def test_response_str_is_complete_and_completion_seconds(full_survey):
    response = Response.objects.create(survey=full_survey["survey"])
    assert response.is_complete is False
    assert response.completion_seconds is None
    assert "response" in str(response).lower()

    response.mark_complete()
    response.save(update_fields=["completed_at"])
    response.refresh_from_db()
    assert response.is_complete is True
    assert response.completion_seconds is not None
    assert response.completion_seconds >= 0


@pytest.mark.django_db
def test_answer_str():
    survey = Survey.objects.create(title="S", slug="s")
    q = Question.objects.create(survey=survey, order=1, text="?", type=Question.Type.SHORT_TEXT)
    response = Response.objects.create(survey=survey)
    answer = Answer.objects.create(response=response, question=q, text_value="hi")
    assert str(answer) == f"{response.id}: {q.id}"


@pytest.mark.django_db
def test_answer_clean_rejects_wrong_typed_columns():
    survey = Survey.objects.create(title="Typed", slug="typed")
    question = Question.objects.create(
        survey=survey, order=1, text="How many?", type=Question.Type.NUMBER
    )
    response = Response.objects.create(survey=survey)
    answer = Answer(response=response, question=question, text_value="wrong", number_value=10)

    with pytest.raises(ValidationError):
        answer.full_clean()


@pytest.mark.django_db
def test_answer_clean_rejects_cross_survey_question(full_survey):
    other = Survey.objects.create(title="Other", slug="other")
    foreign = Question.objects.create(
        survey=other, order=1, text="Else", type=Question.Type.SHORT_TEXT
    )
    response = Response.objects.create(survey=full_survey["survey"])
    answer = Answer(response=response, question=foreign, text_value="x")

    with pytest.raises(ValidationError) as exc:
        answer.full_clean()
    assert "question" in exc.value.error_dict


@pytest.mark.django_db
def test_answer_clean_rating_rejects_text():
    survey = Survey.objects.create(title="R", slug="r")
    q = Question.objects.create(survey=survey, order=1, text="Rate", type=Question.Type.RATING)
    response = Response.objects.create(survey=survey)
    answer = Answer(response=response, question=q, text_value="oops", number_value=3)

    with pytest.raises(ValidationError):
        answer.full_clean()


@pytest.mark.django_db
def test_answer_clean_single_choice_wrong_choice_question():
    survey = Survey.objects.create(title="S", slug="s")
    q1 = Question.objects.create(survey=survey, order=1, text="A", type=Question.Type.SINGLE_CHOICE)
    q2 = Question.objects.create(survey=survey, order=2, text="B", type=Question.Type.SINGLE_CHOICE)
    c2 = Choice.objects.create(question=q2, order=1, label="B1")
    response = Response.objects.create(survey=survey)
    answer = Answer(response=response, question=q1, choice=c2)

    with pytest.raises(ValidationError):
        answer.full_clean()


@pytest.mark.django_db
def test_answer_clean_multiple_choice_rejects_scalar_fields(full_survey):
    response = Response.objects.create(survey=full_survey["survey"])
    answer = Answer(
        response=response,
        question=full_survey["multi"],
        text_value="nope",
    )

    with pytest.raises(ValidationError):
        answer.full_clean()


@pytest.mark.django_db
def test_branch_rule_str_and_clean_rules(branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    rule = BranchRule.objects.get(question=q1, choice=remote)
    assert "Remote" in str(rule) or "remote" in str(rule).lower()

    wrong_type = Question.objects.create(
        survey=survey, order=9, text="Multi", type=Question.Type.MULTIPLE_CHOICE
    )
    choice = Choice.objects.create(question=wrong_type, order=1, label="X")
    bad = BranchRule(question=wrong_type, choice=choice, next_question=q3)
    with pytest.raises(ValidationError):
        bad.save()


@pytest.mark.django_db
def test_branch_rule_rejects_choice_from_other_question(branching_survey):
    survey, q1, q2, q3, _remote = branching_survey
    alien = Choice.objects.create(question=q2, order=99, label="Alien")
    bad = BranchRule(question=q1, choice=alien, next_question=q3)
    with pytest.raises(ValidationError):
        bad.save()


@pytest.mark.django_db
def test_branch_rule_requires_single_choice_question():
    survey = Survey.objects.create(title="Branch", slug="branch")
    source = Question.objects.create(
        survey=survey, order=1, text="Pick many", type=Question.Type.MULTIPLE_CHOICE
    )
    choice = Choice.objects.create(question=source, order=1, label="A")
    target = Question.objects.create(
        survey=survey, order=2, text="Next", type=Question.Type.SHORT_TEXT
    )
    rule = BranchRule(question=source, choice=choice, next_question=target)

    with pytest.raises(ValidationError):
        rule.save()


@pytest.mark.django_db
def test_rating_choices_are_seeded():
    survey = Survey.objects.create(title="Scale", slug="scale")
    question = Question.objects.create(
        survey=survey, order=1, text="Rating", type=Question.Type.RATING
    )

    assert list(question.choices.values_list("label", flat=True)) == ["1", "2", "3", "4", "5"]


@pytest.mark.django_db
def test_likert_choices_are_seeded():
    survey = Survey.objects.create(title="Likert", slug="likert")
    question = Question.objects.create(
        survey=survey, order=1, text="Agree?", type=Question.Type.LIKERT
    )
    labels = list(question.choices.values_list("label", flat=True))
    assert labels == [
        "Strongly disagree",
        "Disagree",
        "Neutral",
        "Agree",
        "Strongly agree",
    ]

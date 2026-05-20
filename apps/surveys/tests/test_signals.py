""" Tests for surveys app signals """

import pytest
from apps.surveys.display import format_answer_value
from apps.surveys.models import Choice, Question, Survey
from apps.surveys.repositories import ResponseRepository
from apps.surveys.signals import LIKERT_LABELS, RATING_LABELS, seed_scale_choices
from django.core.exceptions import ValidationError


@pytest.mark.django_db
def test_rating_signal_seeds_five_choices():
    survey = Survey.objects.create(title="Sig", slug="sig-rating")
    question = Question.objects.create(
        survey=survey, order=1, text="Stars", type=Question.Type.RATING
    )
    assert list(question.choices.values_list("label", flat=True)) == RATING_LABELS


@pytest.mark.django_db
def test_likert_signal_seeds_five_choices():
    survey = Survey.objects.create(title="Sig", slug="sig-likert")
    question = Question.objects.create(
        survey=survey, order=1, text="Scale", type=Question.Type.LIKERT
    )
    assert list(question.choices.values_list("label", flat=True)) == LIKERT_LABELS


@pytest.mark.django_db
def test_signal_does_not_duplicate_existing_choices():
    survey = Survey.objects.create(title="Sig", slug="sig-dup")
    question = Question.objects.create(
        survey=survey, order=1, text="Rate", type=Question.Type.RATING
    )
    Choice.objects.all().delete()
    Choice.objects.create(question=question, order=1, label="Custom")
    seed_scale_choices(sender=Question, instance=question, created=False)
    assert question.choices.count() == 1
    assert question.choices.get().label == "Custom"


@pytest.mark.django_db
def test_signal_ignores_non_scale_types():
    survey = Survey.objects.create(title="Sig", slug="sig-text")
    question = Question.objects.create(
        survey=survey, order=1, text="Name", type=Question.Type.SHORT_TEXT
    )
    assert question.choices.count() == 0


@pytest.mark.django_db
def test_signal_deletes_choices_when_type_no_longer_accepts_choices():
    survey = Survey.objects.create(title="Sig", slug="sig-change")
    question = Question.objects.create(
        survey=survey, order=1, text="Stars", type=Question.Type.RATING
    )
    assert question.choices.count() == 5

    question.type = Question.Type.SHORT_TEXT
    question.save()

    assert question.choices.count() == 0


@pytest.mark.django_db
def test_question_type_change_rejected_when_answers_reference_choices():
    survey = Survey.objects.create(title="Sig", slug="sig-loss")
    question = Question.objects.create(
        survey=survey, order=1, text="Pick", type=Question.Type.SINGLE_CHOICE
    )
    choice = Choice.objects.create(question=question, order=1, label="Some Important Answer")
    response = ResponseRepository.start(survey)
    answer = ResponseRepository.save_answer(response, question, {"value": choice})
    assert format_answer_value(answer) == "Some Important Answer"

    question.type = Question.Type.SHORT_TEXT
    with pytest.raises(ValidationError) as exc:
        question.save()

    assert "answers reference" in str(exc.value).lower()
    question.refresh_from_db()
    assert question.type == Question.Type.SINGLE_CHOICE
    assert Choice.objects.filter(pk=choice.pk).exists()
    answer.refresh_from_db()
    assert answer.choice_id == choice.pk
    assert format_answer_value(answer) == "Some Important Answer"


@pytest.mark.django_db
def test_answers_reference_choices_false_for_unsaved_question():
    question = Question(
        survey=Survey(title="X", slug="x"),
        order=1,
        text="?",
        type=Question.Type.SINGLE_CHOICE,
    )
    assert question.answers_reference_choices() is False


@pytest.mark.django_db
def test_signal_raises_when_cleanup_would_drop_answered_choices(branching_survey):
    survey, q1, *_q2, _q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": remote})
    q1.type = Question.Type.SHORT_TEXT
    with pytest.raises(ValidationError, match="answers reference"):
        seed_scale_choices(sender=Question, instance=q1, created=False)


@pytest.mark.django_db
def test_question_type_change_rejected_for_multiple_choice_answers(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    ResponseRepository.save_answer(
        response,
        full_survey["multi"],
        {"value": [full_survey["multi_a"], full_survey["multi_b"]]},
    )
    question = full_survey["multi"]
    question.type = Question.Type.LONG_TEXT
    with pytest.raises(ValidationError):
        question.save()
    question.refresh_from_db()
    assert question.type == Question.Type.MULTIPLE_CHOICE


@pytest.mark.django_db
def test_signal_replaces_choices_when_converting_single_choice_to_rating():
    survey = Survey.objects.create(title="Sig", slug="sig-to-rating")
    question = Question.objects.create(
        survey=survey, order=1, text="Pick", type=Question.Type.SINGLE_CHOICE
    )
    Choice.objects.create(question=question, order=1, label="Yes")
    Choice.objects.create(question=question, order=2, label="No")

    question.type = Question.Type.RATING
    question.save()

    assert list(question.choices.order_by("order").values_list("label", flat=True)) == RATING_LABELS


@pytest.mark.django_db
def test_signal_deletes_single_choice_options_when_changed_to_text():
    survey = Survey.objects.create(title="Sig", slug="sig-single")
    question = Question.objects.create(
        survey=survey, order=1, text="Pick", type=Question.Type.SINGLE_CHOICE
    )
    Choice.objects.create(question=question, order=1, label="Yes")
    Choice.objects.create(question=question, order=2, label="No")

    question.type = Question.Type.LONG_TEXT
    question.save()

    assert question.choices.count() == 0

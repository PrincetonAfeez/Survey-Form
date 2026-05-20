import pytest
from apps.surveys.models import Choice, Question, Survey
from apps.surveys.signals import LIKERT_LABELS, RATING_LABELS, seed_scale_choices


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

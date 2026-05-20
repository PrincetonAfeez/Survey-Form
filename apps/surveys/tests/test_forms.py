from datetime import date
from decimal import Decimal

import pytest
from apps.surveys.lib import trim_decimal
from apps.surveys.forms import QuestionForm, _initial_for, form_for_question
from apps.surveys.models import Answer, Question
from apps.surveys.repositories import ResponseRepository


@pytest.mark.django_db
def test_question_form_stores_question_reference(full_survey):
    form = form_for_question(full_survey["short"])
    assert isinstance(form, QuestionForm)
    assert form.question == full_survey["short"]
    assert form.fields["value"].label == "Name"


@pytest.mark.django_db
def test_form_required_validation(full_survey):
    form = form_for_question(full_survey["short"], data={})
    assert form.is_valid() is False
    assert "value" in form.errors


@pytest.mark.django_db
def test_form_optional_long_text_allows_empty(full_survey):
    form = form_for_question(full_survey["long"], data={"value": ""})
    assert form.is_valid() is True


@pytest.mark.django_db
def test_form_short_text_max_length(full_survey):
    form = form_for_question(full_survey["short"], data={"value": "x" * 256})
    assert form.is_valid() is False


@pytest.mark.django_db
def test_form_number_and_date_validation(full_survey):
    number_form = form_for_question(full_survey["number"], data={"value": "not-a-number"})
    assert number_form.is_valid() is False

    date_form = form_for_question(full_survey["date"], data={"value": "bad-date"})
    assert date_form.is_valid() is False

    good_date = form_for_question(full_survey["date"], data={"value": "2026-05-16"})
    assert good_date.is_valid() is True
    assert good_date.cleaned_data["value"] == date(2026, 5, 16)


@pytest.mark.django_db
def test_form_choice_fields_require_valid_pk(full_survey):
    form = form_for_question(full_survey["single"], data={"value": "99999"})
    assert form.is_valid() is False


@pytest.mark.django_db
def test_initial_for_all_types(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    payloads = {
        "short": "Ada",
        "long": "Story",
        "number": "4.5",
        "date": date(2026, 1, 2),
        "single": full_survey["single_yes"],
        "multi": [full_survey["multi_a"], full_survey["multi_b"]],
        "rating": full_survey["rating"].choices.get(label="4"),
        "likert": full_survey["likert"].choices.get(label="Agree"),
    }
    for key, value in payloads.items():
        question = full_survey[key]
        if key == "multi":
            cleaned = {"value": value}
        else:
            cleaned = {"value": value}
        answer = ResponseRepository.save_answer(response, question, cleaned)

    for key in payloads:
        question = full_survey[key]
        answer = Answer.objects.get(response=response, question=question)
        initial = _initial_for(answer)
        assert initial is not None


@pytest.mark.django_db
def test_initial_for_rating_matches_choice_label(full_survey):
    response = ResponseRepository.start(full_survey["survey"])
    choice = full_survey["rating"].choices.get(label="3")
    answer = ResponseRepository.save_answer(response, full_survey["rating"], {"value": choice})
    assert _initial_for(answer) == choice.id


@pytest.mark.django_db
def test_initial_for_empty_instance():
    assert _initial_for(None) is None


@pytest.mark.django_db
def test_trim_decimal_strips_trailing_zeros():
    assert trim_decimal(Decimal("3.50")) == "3.5"
    assert trim_decimal(Decimal("4")) == "4"


@pytest.mark.django_db
def test_form_for_unsupported_type_raises():
    from apps.surveys.models import Survey

    survey = Survey.objects.create(title="Bad", slug="bad-type")
    q = Question.objects.create(
        survey=survey, order=1, text="?", type=Question.Type.SHORT_TEXT
    )
    Question.objects.filter(pk=q.pk).update(type="not_real")
    q.refresh_from_db()
    with pytest.raises(ValueError, match="Unsupported"):
        form_for_question(q)

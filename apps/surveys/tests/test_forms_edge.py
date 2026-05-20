"""Tests for surveys app forms edge cases"""

from decimal import Decimal

import pytest
from apps.surveys.forms import _initial_for, form_for_question
from apps.surveys.models import Answer, Question, Response, Survey


@pytest.mark.django_db
def test_initial_for_number_not_rating():
    survey = Survey.objects.create(title="N", slug="n-init")
    q = Question.objects.create(survey=survey, order=1, text="Num", type=Question.Type.NUMBER)
    response = Response.objects.create(survey=survey)
    answer = Answer.objects.create(response=response, question=q, number_value=Decimal("7.25"))
    assert _initial_for(answer) == Decimal("7.25")


@pytest.mark.django_db
def test_initial_for_multiple_without_pk():
    survey = Survey.objects.create(title="M", slug="m-init")
    q = Question.objects.create(
        survey=survey, order=1, text="Multi", type=Question.Type.MULTIPLE_CHOICE
    )
    response = Response.objects.create(survey=survey)
    answer = Answer(response=response, question=q)
    assert _initial_for(answer) is None


@pytest.mark.django_db
def test_form_rating_widget(full_survey):
    form = form_for_question(full_survey["rating"])
    assert "RadioSelect" in form.fields["value"].widget.__class__.__name__


@pytest.mark.django_db
def test_initial_rating_choice_id_none_without_number_value(full_survey):
    from apps.surveys.forms import _initial_rating_choice_id

    response = Response.objects.create(survey=full_survey["survey"])
    answer = Answer(
        response=response,
        question=full_survey["rating"],
        number_value=None,
    )
    assert _initial_rating_choice_id(answer) is None


@pytest.mark.django_db
def test_initial_rating_choice_id_matches_via_rating_value(full_survey):
    from apps.surveys.forms import _initial_rating_choice_id

    question = full_survey["rating"]
    choice = question.choices.get(label="5")
    response = Response.objects.create(survey=full_survey["survey"])
    answer = Answer.objects.create(
        response=response,
        question=question,
        number_value=Decimal("5"),
    )
    assert _initial_rating_choice_id(answer) == choice.id


@pytest.mark.django_db
def test_initial_for_rating_returns_none_when_choice_unmatched(full_survey, monkeypatch):
    from apps.surveys.forms import _initial_for

    question = full_survey["rating"]
    response = Response.objects.create(survey=full_survey["survey"])
    answer = Answer.objects.create(
        response=response,
        question=question,
        number_value=Decimal("99"),
    )
    monkeypatch.setattr("apps.surveys.forms.rating_value", lambda _choice: None)
    assert _initial_for(answer) is None


@pytest.mark.django_db
def test_initial_rating_choice_id_falls_back_to_label(full_survey, monkeypatch):
    from apps.surveys import forms as forms_module
    from apps.surveys.forms import _initial_rating_choice_id

    question = full_survey["rating"]
    question.choices.all().delete()
    choice = question.choices.create(label="7", order=5)
    response = Response.objects.create(survey=full_survey["survey"])
    answer = Answer.objects.create(
        response=response,
        question=question,
        number_value=Decimal("7"),
    )
    monkeypatch.setattr(forms_module, "rating_value", lambda _choice: None)
    assert _initial_rating_choice_id(answer) == choice.id

    form = form_for_question(question, instance=answer)
    assert form.fields["value"].initial == choice.id

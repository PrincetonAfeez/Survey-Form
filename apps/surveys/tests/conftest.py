"""Test fixtures for surveys app."""

import pytest
from apps.surveys.models import BranchRule, Choice, Question, Survey


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="secret", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="user", password="secret")


@pytest.fixture
def branching_survey(db):
    survey = Survey.objects.create(title="Branching survey", slug="branching", is_published=False)
    q1 = Question.objects.create(
        survey=survey,
        order=1,
        text="Work style?",
        type=Question.Type.SINGLE_CHOICE,
    )
    remote = Choice.objects.create(question=q1, order=1, label="Remote")
    Choice.objects.create(question=q1, order=2, label="Office")
    q2 = Question.objects.create(
        survey=survey,
        order=2,
        text="Commute minutes?",
        type=Question.Type.NUMBER,
        is_required=False,
    )
    q3 = Question.objects.create(
        survey=survey,
        order=3,
        text="Workspace rating?",
        type=Question.Type.RATING,
    )
    BranchRule.objects.create(question=q1, choice=remote, next_question=q3)
    survey.is_published = True
    survey.save()
    return survey, q1, q2, q3, remote


@pytest.fixture
def unpublished_survey(db):
    return Survey.objects.create(title="Draft", slug="draft", is_published=False)


@pytest.fixture
def full_survey(db):
    survey = Survey.objects.create(title="Full", slug="full", is_published=False)
    short = Question.objects.create(
        survey=survey, order=1, text="Name", type=Question.Type.SHORT_TEXT
    )
    long_q = Question.objects.create(
        survey=survey, order=2, text="Story", type=Question.Type.LONG_TEXT, is_required=False
    )
    number = Question.objects.create(
        survey=survey, order=3, text="Count", type=Question.Type.NUMBER
    )
    when = Question.objects.create(survey=survey, order=4, text="Date", type=Question.Type.DATE)
    single = Question.objects.create(
        survey=survey, order=5, text="Pick one", type=Question.Type.SINGLE_CHOICE
    )
    single_yes = Choice.objects.create(question=single, order=1, label="Yes")
    Choice.objects.create(question=single, order=2, label="No")
    multi = Question.objects.create(
        survey=survey, order=6, text="Pick many", type=Question.Type.MULTIPLE_CHOICE
    )
    multi_a = Choice.objects.create(question=multi, order=1, label="A")
    multi_b = Choice.objects.create(question=multi, order=2, label="B")
    rating = Question.objects.create(
        survey=survey, order=7, text="Rate it", type=Question.Type.RATING
    )
    likert = Question.objects.create(
        survey=survey, order=8, text="Agree?", type=Question.Type.LIKERT
    )
    survey.is_published = True
    survey.save()
    return {
        "survey": survey,
        "short": short,
        "long": long_q,
        "number": number,
        "date": when,
        "single": single,
        "single_yes": single_yes,
        "multi": multi,
        "multi_a": multi_a,
        "multi_b": multi_b,
        "rating": rating,
        "likert": likert,
    }

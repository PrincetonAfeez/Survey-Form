""" Tests for surveys app managers """

import pytest
from apps.surveys.models import Answer, Question, Response, Survey


@pytest.mark.django_db
def test_survey_queryset_published_filters_drafts():
    pub = Survey.objects.create(title="Pub", slug="pub", is_published=False)
    Question.objects.create(
        survey=pub, order=1, text="Q", type=Question.Type.SHORT_TEXT
    )
    pub.is_published = True
    pub.save()
    Survey.objects.create(title="Draft", slug="draft", is_published=False)

    assert Survey.objects.published().count() == 1
    assert Survey.objects.published().get().slug == "pub"


@pytest.mark.django_db
def test_response_queryset_complete_and_for_survey(branching_survey):
    survey, *_ = branching_survey
    Response.objects.create(survey=survey)
    done = Response.objects.create(survey=survey)
    done.mark_complete()
    done.save(update_fields=["completed_at"])
    other = Survey.objects.create(title="Other", slug="other", is_published=False)
    Question.objects.create(
        survey=other, order=1, text="Q", type=Question.Type.SHORT_TEXT
    )
    other.is_published = True
    other.save()
    Response.objects.create(survey=other)

    scoped = Response.objects.for_survey(survey)
    assert scoped.count() == 2
    assert Response.objects.for_survey(survey).complete().count() == 1


@pytest.mark.django_db
def test_answer_queryset_for_question(branching_survey):
    survey, q1, *_ = branching_survey
    response = Response.objects.create(survey=survey)
    Answer.objects.create(response=response, question=q1, text_value="")

    assert Answer.objects.for_question(q1).count() == 1
    assert Answer.objects.for_question(q1).first().response_id == response.id


@pytest.mark.django_db
def test_answer_queryset_for_completed_question(branching_survey):
    from apps.surveys.repositories import ResponseRepository

    survey, q1, *_ = branching_survey
    remote = q1.choices.first()
    draft = ResponseRepository.start(survey)
    ResponseRepository.save_answer(draft, q1, {"value": remote})
    done = ResponseRepository.start(survey)
    ResponseRepository.save_answer(done, q1, {"value": remote})
    ResponseRepository.complete(done)

    assert Answer.objects.for_question(q1).count() == 2
    assert Answer.objects.for_completed_question(q1).count() == 1

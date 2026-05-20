import pytest
from apps.surveys.repositories import ResponseRepository
from apps.surveys.tokens import (
    DEFAULT_MAX_AGE,
    RESUME_SALT,
    issue_resume_token,
    verify_resume_token,
)
from django.core import signing


@pytest.mark.django_db
def test_resume_token_round_trip(branching_survey):
    survey, *_ = branching_survey
    response = ResponseRepository.start(survey)
    token = issue_resume_token(response)

    payload = verify_resume_token(token)

    assert payload == {
        "r": str(response.uuid),
        "s": survey.id,
        "n": str(response.resume_nonce),
    }


@pytest.mark.django_db
def test_resume_token_rejects_tampering(branching_survey):
    survey, *_ = branching_survey
    response = ResponseRepository.start(survey)
    token = issue_resume_token(response) + "tampered"

    assert verify_resume_token(token) is None


@pytest.mark.django_db
def test_resume_token_rejects_wrong_salt(branching_survey):
    survey, *_ = branching_survey
    response = ResponseRepository.start(survey)
    token = signing.dumps(
        {"r": str(response.uuid), "s": survey.id},
        salt="wrong.salt",
    )
    assert verify_resume_token(token) is None


@pytest.mark.django_db
def test_resume_token_respects_max_age(branching_survey):
    survey, *_ = branching_survey
    response = ResponseRepository.start(survey)
    token = issue_resume_token(response)
    assert verify_resume_token(token, max_age=DEFAULT_MAX_AGE) is not None
    assert verify_resume_token(token, max_age=0) is None


@pytest.mark.django_db
def test_resume_salt_constant():
    assert RESUME_SALT == "survey.resume"


@pytest.mark.django_db
def test_resume_rejects_token_without_nonce(branching_survey, client):
    from django.urls import reverse

    survey, *_ = branching_survey
    response = ResponseRepository.start(survey)
    token = signing.dumps(
        {"r": str(response.uuid), "s": survey.id},
        salt=RESUME_SALT,
    )
    result = client.get(reverse("surveys:resume", args=[survey.slug, token]))
    assert result.status_code == 400


@pytest.mark.django_db
def test_is_resume_allowed_for_complete_response(branching_survey):
    survey, q1, *_rest, remote = branching_survey
    older = ResponseRepository.start(survey)
    ResponseRepository.save_answer(older, q1, {"value": remote})
    ResponseRepository.complete(older)
    newer = ResponseRepository.start(survey)
    assert ResponseRepository.is_resume_allowed(survey, older)
    assert ResponseRepository.is_resume_allowed(survey, newer)

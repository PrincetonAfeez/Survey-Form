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

    assert payload == {"r": str(response.uuid), "s": survey.id}


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

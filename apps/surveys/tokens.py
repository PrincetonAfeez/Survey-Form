from django.core import signing

from .models import Response

RESUME_SALT = "survey.resume"
DEFAULT_MAX_AGE = 60 * 60 * 24 * 30


def issue_resume_token(response: Response) -> str:
    return signing.dumps({"r": str(response.uuid), "s": response.survey_id}, salt=RESUME_SALT)


def verify_resume_token(token: str, *, max_age: int = DEFAULT_MAX_AGE) -> dict | None:
    try:
        return signing.loads(token, salt=RESUME_SALT, max_age=max_age)
    except signing.BadSignature:
        return None

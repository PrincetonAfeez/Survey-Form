import pytest
from apps.surveys.models import BranchRule, Survey
from django.contrib.auth import get_user_model
from django.core.management import call_command


@pytest.mark.django_db
def test_seed_survey_creates_demo():
    call_command("seed_survey")
    survey = Survey.objects.get(slug="remote-work-readiness")
    assert survey.is_published is True
    assert survey.questions.count() >= 5
    assert BranchRule.objects.filter(question__survey=survey).exists()


@pytest.mark.django_db
def test_seed_survey_with_admin_creates_superuser():
    call_command("seed_survey", "--with-admin")
    User = get_user_model()
    admin = User.objects.get(username="admin")
    assert admin.is_superuser is True


@pytest.mark.django_db
def test_seed_survey_idempotent_admin():
    User = get_user_model()
    User.objects.create_superuser(username="admin", email="a@b.com", password="x")
    call_command("seed_survey", "--with-admin")
    assert User.objects.filter(username="admin").count() == 1


@pytest.mark.django_db
def test_seed_survey_replaces_questions():
    call_command("seed_survey")
    first_count = Survey.objects.get(slug="remote-work-readiness").questions.count()
    call_command("seed_survey")
    second_count = Survey.objects.get(slug="remote-work-readiness").questions.count()
    assert first_count == second_count

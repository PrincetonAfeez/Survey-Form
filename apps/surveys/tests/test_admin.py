import pytest
from apps.surveys.admin import AnswerInline, BranchRuleAdmin, SurveyAdmin
from apps.surveys.models import Answer, BranchRule, Question, Survey
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import RequestFactory


@pytest.mark.django_db
def test_branch_rule_admin_save_calls_full_clean(branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    site = AdminSite()
    admin = BranchRuleAdmin(BranchRule, site)
    factory = RequestFactory()
    request = factory.get("/")
    request.user = get_user_model().objects.create_superuser(
        username="admin", email="a@a.com", password="x"
    )

    bad = BranchRule(question=q1, choice=remote, next_question=q3)
    bad.question = q1
    # Force invalid: point to wrong survey
    other = Survey.objects.create(title="X", slug="x-admin")
    foreign = Question.objects.create(
        survey=other, order=1, text="F", type=Question.Type.SHORT_TEXT
    )
    bad.next_question = foreign

    with pytest.raises(ValidationError):
        admin.save_model(request, bad, form=None, change=False)


@pytest.mark.django_db
def test_survey_clean_allows_published_flag_before_save():
    survey = Survey(title="New", slug="new-unsaved", is_published=True)
    survey.full_clean()


@pytest.mark.django_db
def test_survey_admin_add_form_published_without_pk_is_valid():
    site = AdminSite()
    admin = SurveyAdmin(Survey, site)
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.create_superuser(
        username="formadmin", email="f@f.com", password="x"
    )
    form_class = admin.get_form(request)
    form = form_class(
        data={
            "title": "New survey",
            "slug": "new-survey-admin",
            "intro": "",
            "is_published": True,
        }
    )
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_survey_admin_response_change_invalid_publish_shows_message_not_500():
    from django.contrib.messages.storage.fallback import FallbackStorage

    survey = Survey.objects.create(title="Bad", slug="bad-publish", is_published=True)
    Question.objects.create(
        survey=survey,
        order=1,
        text="Pick many",
        type=Question.Type.MULTIPLE_CHOICE,
    )
    site = AdminSite()
    admin = SurveyAdmin(Survey, site)
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.create_superuser(
        username="super", email="s@s.com", password="x"
    )
    request.session = {}
    request._messages = FallbackStorage(request)

    response = admin.response_change(request, survey)

    assert response.status_code == 302
    survey.refresh_from_db()
    assert survey.is_published is False
    msgs = [str(m) for m in get_messages(request)]
    assert any("choice" in m.lower() or "published" in m.lower() for m in msgs)


@pytest.mark.django_db
def test_survey_admin_preview_and_results_links():
    survey = Survey.objects.create(title="Admin", slug="admin-survey")
    site = AdminSite()
    admin = SurveyAdmin(Survey, site)
    preview_html = admin.preview(survey)
    results_html = admin.results(survey)
    assert "admin-survey" in preview_html or "/s/admin-survey" in preview_html
    assert str(survey.id) in results_html


@pytest.mark.django_db
def test_answer_inline_multi_choices_display(full_survey):
    from apps.surveys.repositories import ResponseRepository

    response = ResponseRepository.start(full_survey["survey"])
    ResponseRepository.save_answer(
        response,
        full_survey["multi"],
        {"value": [full_survey["multi_a"], full_survey["multi_b"]]},
    )
    answer = response.answers.get(question=full_survey["multi"])
    inline = AnswerInline(Answer, AdminSite())
    assert "A" in inline.multi_choices_display(answer)
    assert "B" in inline.multi_choices_display(answer)

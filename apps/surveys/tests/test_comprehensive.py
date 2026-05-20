"""Broad unit and integration tests for modules, helpers, and edge branches."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from apps.surveys.admin import (
    QuestionAdmin,
    SurveyAdmin,
    ValidateAfterSaveMixin,
    _format_validation_error,
)
from apps.surveys.forms import _initial_rating_choice_id
from apps.surveys.models import Answer, BranchRule, Choice, Question, Response, Survey
from apps.surveys.navigation import choice_from_saved_response, next_question
from apps.surveys.pathing import branch_rule_creates_cycle
from apps.surveys.repositories import ResponseRepository, SurveyRepository
from apps.surveys.runners import SurveyRunner
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseRedirect
from django.test import RequestFactory
from django.urls import reverse


# --- admin.py ---


def test_format_validation_error_messages_list():
    exc = ValidationError(["First problem.", "Second problem."])
    text = _format_validation_error(exc)
    assert "First problem" in text
    assert "Second problem" in text


def test_format_validation_error_plain_string():
    assert _format_validation_error(ValidationError("plain")) == "plain"


def test_format_validation_error_str_fallback_without_dict_or_messages():
    class Bare(ValidationError):
        @property
        def error_dict(self):
            raise AttributeError

        @property
        def messages(self):
            raise AttributeError

    exc = Bare("fallback")
    assert _format_validation_error(exc) == str(exc)


@pytest.mark.django_db
def test_format_validation_error_error_dict():
    exc = ValidationError({"is_published": ["Cannot publish."]})
    text = _format_validation_error(exc)
    assert "Cannot publish" in text


@pytest.mark.django_db
def test_survey_admin_validate_saved_instance_returns_true(branching_survey):
    survey, *_ = branching_survey
    site = AdminSite()
    admin = SurveyAdmin(Survey, site)
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.create_superuser(
        username="valid", email="v@v.com", password="x"
    )
    assert admin._validate_saved_instance(request, survey) is True


@pytest.mark.django_db
def test_survey_admin_response_change_success_calls_super(branching_survey):
    survey, *_ = branching_survey
    site = AdminSite()
    admin = SurveyAdmin(Survey, site)
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.create_superuser(
        username="super2", email="s2@s.com", password="x"
    )
    request.session = {}
    request._messages = FallbackStorage(request)

    with patch(
        "django.contrib.admin.ModelAdmin.response_change",
        return_value=HttpResponse("ok"),
    ) as mock_super:
        response = admin.response_change(request, survey)

    mock_super.assert_called_once()
    assert response.status_code == 200


@pytest.mark.django_db
def test_survey_admin_response_add_invalid_redirects():
    survey = Survey.objects.create(
        title="Add invalid", slug="add-invalid", is_published=True
    )
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
        username="adder", email="a@a.com", password="x"
    )
    request.session = {}
    request._messages = FallbackStorage(request)

    response = admin.response_add(request, survey)

    assert isinstance(response, HttpResponseRedirect)
    survey.refresh_from_db()
    assert survey.is_published is False


@pytest.mark.django_db
def test_survey_admin_response_add_success_calls_super(branching_survey):
    survey, *_ = branching_survey
    site = AdminSite()
    admin = SurveyAdmin(Survey, site)
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.create_superuser(
        username="adder2", email="a2@a.com", password="x"
    )
    request.session = {}
    request._messages = FallbackStorage(request)

    with patch(
        "django.contrib.admin.ModelAdmin.response_add",
        return_value=HttpResponse("created"),
    ) as mock_super:
        response = admin.response_add(request, survey)

    mock_super.assert_called_once()
    assert response.status_code == 200


@pytest.mark.django_db
def test_question_admin_inlines_and_short_text(full_survey):
    site = AdminSite()
    admin = QuestionAdmin(Question, site)
    request = RequestFactory().get("/")

    assert admin.get_inlines(request, full_survey["short"]) == []
    assert len(admin.get_inlines(request, full_survey["single"])) == 1
    assert len(admin.get_inlines(request, full_survey["multi"])) == 1

    long_text = "x" * 100
    question = full_survey["short"]
    question.text = long_text
    assert admin.short_text(question) == long_text[:80]


@pytest.mark.django_db
def test_validate_after_save_mixin_revert_skips_non_survey():
    mixin = ValidateAfterSaveMixin()
    question = Question.objects.create(
        survey=Survey.objects.create(title="Q", slug="q-mixin"),
        order=1,
        text="?",
        type=Question.Type.SHORT_TEXT,
    )
    mixin._revert_invalid_publish(question)


# --- navigation.py ---


@pytest.mark.django_db
def test_choice_from_saved_response_without_pk(branching_survey):
    survey, q1, *_ = branching_survey
    response = Response(survey=survey, current_step=1)
    assert choice_from_saved_response(response, q1) is None


@pytest.mark.django_db
def test_choice_from_saved_response_non_single(branching_survey):
    survey, _q1, q2, *_ = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q2, {"value": Decimal("5")})
    assert choice_from_saved_response(response, q2) is None


@pytest.mark.django_db
def test_choice_from_saved_response_returns_choice(branching_survey):
    survey, q1, *_q2, _q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": remote})
    assert choice_from_saved_response(response, q1) == remote


@pytest.mark.django_db
def test_next_question_skips_branch_for_non_single(full_survey):
    survey = full_survey["survey"]
    nxt = next_question(survey, full_survey["short"], None)
    assert nxt == full_survey["long"]


# --- pathing.py ---


@pytest.mark.django_db
def test_branch_rule_creates_cycle_false_when_incomplete_rule(branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    rule = BranchRule(question=q1, choice=remote, next_question=q3)
    rule.next_question_id = None
    assert branch_rule_creates_cycle(rule) is False

    bare = BranchRule()
    assert branch_rule_creates_cycle(bare) is False


# --- repositories.py ---


@pytest.mark.django_db
def test_prune_answers_off_path_empty_path_returns_zero(branching_survey):
    survey, _q1, q2, *_ = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q2, {"value": Decimal("10")})
    assert ResponseRepository.prune_answers_off_path(response, []) == 0
    assert response.answers.count() == 1


# --- forms.py ---


@pytest.mark.django_db
def test_initial_rating_choice_id_label_fallback(full_survey):
    question = full_survey["rating"]
    question.choices.all().delete()
    Choice.objects.create(question=question, order=99, label="7")
    response = ResponseRepository.start(full_survey["survey"])
    answer = Answer.objects.create(
        response=response,
        question=question,
        number_value=Decimal("7"),
    )
    assert _initial_rating_choice_id(answer) == question.choices.get(label="7").id


# --- runners.py ---


@pytest.mark.django_db
def test_runner_has_next_step_and_is_final(branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)

    assert runner.has_next_step(q1) is True
    assert runner.is_final_step(q3) is True

    ResponseRepository.save_answer(response, q1, {"value": remote})
    assert runner.has_next_step(q1) is True
    runner.submit({"value": str(q3.choices.get(label="5").id)}, step=q3.order)
    response.refresh_from_db()
    assert runner.is_final_step(q3) is True
    assert runner.has_next_step(q3) is False


@pytest.mark.django_db
def test_runner_branch_choice_with_non_choice_value(full_survey):
    assert (
        SurveyRunner._branch_choice(full_survey["single"], {"value": "not-a-choice"})
        is None
    )


@pytest.mark.django_db
def test_runner_choice_from_saved_answer_preview_mode(branching_survey):
    survey, q1, *_ = branching_survey
    runner = SurveyRunner(
        survey, Response(survey=survey, current_step=1), record=False
    )
    assert runner.choice_from_saved_answer(q1) is None


# --- views.py helpers ---


@pytest.mark.django_db
def test_record_forward_appends_from_order_when_tail_differs(branching_survey):
    from apps.surveys.views import _record_forward

    survey, q1, q2, q3, _remote = branching_survey
    factory = RequestFactory()
    request = factory.get("/")
    request.session = {f"survey_path_{survey.id}": [q1.order]}
    _record_forward(request, survey, q2.order, q3.order, preview=False)
    assert request.session[f"survey_path_{survey.id}"] == [q1.order, q2.order, q3.order]


@pytest.mark.django_db
def test_path_helpers_preview_prefix(branching_survey):
    from apps.surveys.views import _get_path, _init_path, _path_key, _set_path

    survey, q1, *_ = branching_survey
    factory = RequestFactory()
    request = factory.get("/")
    request.session = {}

    assert _path_key(survey, preview=True) == f"survey_preview_path_{survey.id}"
    _init_path(request, survey, q1.order, preview=True)
    assert _get_path(request, survey, preview=True) == [q1.order]
    _set_path(request, survey, [q1.order, 2], preview=True)
    assert _get_path(request, survey, preview=True) == [q1.order, 2]


@pytest.mark.django_db
def test_done_redirects_incomplete_session(client, branching_survey):
    survey, *_ = branching_survey
    response = client.get(reverse("surveys:done", args=[survey.slug]))
    assert response.status_code == 302
    assert reverse("surveys:intro", args=[survey.slug]) in response["Location"]


@pytest.mark.django_db
def test_start_survey_force_new(client, branching_survey):
    survey, q1, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    response = client.post(
        reverse("surveys:start", args=[survey.slug]),
        {"force_new": "1"},
    )
    assert response.status_code == 302
    assert survey.responses.count() == 2


@pytest.mark.django_db
def test_preview_step_redirects_when_question_missing(staff_user, client, branching_survey):
    survey, q1, *_ = branching_survey
    client.force_login(staff_user)
    client.get(reverse("surveys:preview", args=[survey.slug]))
    q1.delete()
    response = client.get(reverse("surveys:preview_step", args=[survey.slug, 1]))
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:preview", args=[survey.slug]))


@pytest.mark.django_db
def test_export_csv_includes_answer_columns(staff_user, client, full_survey):
    survey = full_survey["survey"]
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, full_survey["short"], {"value": "Ada"})
    ResponseRepository.complete(response)
    client.force_login(staff_user)
    result = client.get(reverse("surveys:export_csv", args=[survey.id]))
    assert result.status_code == 200
    assert b"Ada" in result.content
    assert b"response_uuid" in result.content


@pytest.mark.django_db
def test_results_raw_htmx_partial(staff_user, client, branching_survey):
    survey, *_ = branching_survey
    client.force_login(staff_user)
    response = client.get(
        reverse("surveys:results_raw", args=[survey.id]),
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert b"<table" in response.content.lower() or b"table" in response.content.lower()

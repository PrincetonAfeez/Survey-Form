"""Targeted tests for remaining uncovered lines (99%+ goal)."""

import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from apps.surveys.admin import AnswerInline, BranchRuleAdmin
from apps.surveys.display import format_answer_value
from apps.surveys.forms import form_for_question
from apps.surveys.models import Answer, BranchRule, Question, Response, Survey
from apps.surveys.repositories import ResponseRepository
from apps.surveys.runners import SurveyRunner
from apps.surveys.tokens import RESUME_SALT
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.urls import reverse

# --- views.py ---


@pytest.mark.django_db
def test_step_raises_404_when_question_order_missing(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    response = survey.responses.get()
    response.current_step = 99
    response.save(update_fields=["current_step"])
    result = client.get(reverse("surveys:step", args=[survey.slug, 99]))
    assert result.status_code == 404


@pytest.mark.django_db
def test_resume_invalid_when_response_uuid_unknown(client, branching_survey):
    survey, *_ = branching_survey
    token = signing.dumps(
        {"r": str(uuid.uuid4()), "s": survey.id},
        salt=RESUME_SALT,
    )
    response = client.get(reverse("surveys:resume", args=[survey.slug, token]))
    assert response.status_code == 400
    assert b"invalid or expired" in response.content


@pytest.mark.django_db
def test_resume_invalid_when_response_belongs_to_other_survey(client, branching_survey):
    survey, *_ = branching_survey
    other = Survey.objects.create(title="Other", slug="other-cov", is_published=True)
    Question.objects.create(
        survey=other, order=1, text="Other Q", type=Question.Type.SHORT_TEXT
    )
    foreign = ResponseRepository.start(other)
    # Token claims survey A but points at a response for survey B.
    token = signing.dumps({"r": str(foreign.uuid), "s": survey.id}, salt=RESUME_SALT)
    response = client.get(reverse("surveys:resume", args=[survey.slug, token]))
    assert response.status_code == 400


@pytest.mark.django_db
def test_preview_step_404_for_unknown_slug(staff_user, client):
    client.force_login(staff_user)
    response = client.get(reverse("surveys:preview_step", args=["no-such-slug", 1]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_staff_exports_404_for_unknown_survey(staff_user, client):
    client.force_login(staff_user)
    for name in ("results_raw", "export_csv", "export_json"):
        response = client.get(reverse(f"surveys:{name}", args=[99999]))
        assert response.status_code == 404


@pytest.mark.django_db
def test_preview_final_non_htmx_redirect(client, branching_survey, staff_user):
    survey, _q1, _q2, q3, remote = branching_survey
    client.force_login(staff_user)
    client.post(
        reverse("surveys:preview_step", args=[survey.slug, 1]),
        {"value": remote.id},
    )
    response = client.post(
        reverse("surveys:preview_step", args=[survey.slug, q3.order]),
        {"value": q3.choices.get(label="5").id},
    )
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:preview", args=[survey.slug]))


@pytest.mark.django_db
def test_session_cleared_when_uuid_points_to_other_survey(client, branching_survey):
    survey, *_ = branching_survey
    other = Survey.objects.create(title="Other", slug="other-sess", is_published=True)
    Question.objects.create(
        survey=other, order=1, text="Other Q", type=Question.Type.SHORT_TEXT
    )
    foreign = ResponseRepository.start(other)
    session = client.session
    session[f"survey_response_{survey.id}"] = str(foreign.uuid)
    session.save()

    response = client.get(reverse("surveys:step", args=[survey.slug, 1]))
    assert response.status_code == 302
    assert reverse("surveys:intro", args=[survey.slug]) in response["Location"]


@pytest.mark.django_db
def test_session_cleared_when_uuid_is_unknown(client, branching_survey):
    survey, *_ = branching_survey
    session = client.session
    session[f"survey_response_{survey.id}"] = str(uuid.uuid4())
    session.save()

    response = client.get(reverse("surveys:step", args=[survey.slug, 1]))
    assert response.status_code == 302


@pytest.mark.django_db
def test_results_raw_full_page_not_htmx(staff_user, branching_survey, client):
    survey, *_ = branching_survey
    client.force_login(staff_user)
    response = client.get(reverse("surveys:results_raw", args=[survey.id]))
    assert response.status_code == 200
    assert b"Raw responses" in response.content


@pytest.mark.django_db
def test_export_json_with_completed_answer(branching_survey, staff_user, client):
    survey, q1, _q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": remote})
    ResponseRepository.save_answer(response, q3, {"value": q3.choices.get(label="4")})
    ResponseRepository.complete(response)
    client.force_login(staff_user)
    payload = json.loads(
        client.get(reverse("surveys:export_json", args=[survey.id])).content
    )
    assert payload[0]["answers"]


# --- admin.py ---


@pytest.mark.django_db
def test_branch_rule_admin_save_valid_rule(branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    site = AdminSite()
    admin = BranchRuleAdmin(BranchRule, site)
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.create_superuser(
        username="saver", email="s@s.com", password="x"
    )
    rule = BranchRule.objects.get(question=q1, choice=remote)
    admin.save_model(request, rule, form=None, change=True)


@pytest.mark.django_db
def test_answer_inline_multi_display_empty_for_unsaved():
    inline = AnswerInline(Answer, AdminSite())
    assert inline.multi_choices_display(Answer()) == ""


# --- display.py ---


@pytest.mark.django_db
def test_format_answer_value_unknown_question_type():
    survey = Survey.objects.create(title="U", slug="u-display")
    q = Question.objects.create(survey=survey, order=1, text="?", type=Question.Type.SHORT_TEXT)
    q.type = "unknown_type"
    response = Response.objects.create(survey=survey)
    answer = Answer.objects.create(response=response, question=q, text_value="x")
    assert format_answer_value(answer) == ""


# --- forms.py ---


@pytest.mark.django_db
def test_form_multiple_choice_field_config(full_survey):
    form = form_for_question(full_survey["multi"])
    field = form.fields["value"]
    assert field.__class__.__name__ == "ModelMultipleChoiceField"
    assert field.required is True


# --- models.py ---


@pytest.mark.django_db
def test_answer_clean_long_text_rejects_extra_columns(full_survey):
    response = Response.objects.create(survey=full_survey["survey"])
    answer = Answer(
        response=response,
        question=full_survey["long"],
        text_value="ok",
        number_value=Decimal("1"),
    )
    with pytest.raises(ValidationError) as exc:
        answer.full_clean()
    assert "text_value" in exc.value.error_dict


@pytest.mark.django_db
def test_answer_clean_date_rejects_extra_columns(full_survey):
    response = Response.objects.create(survey=full_survey["survey"])
    answer = Answer(
        response=response,
        question=full_survey["date"],
        date_value=date(2026, 1, 1),
        text_value="nope",
    )
    with pytest.raises(ValidationError) as exc:
        answer.full_clean()
    assert "date_value" in exc.value.error_dict


@pytest.mark.django_db
def test_answer_clean_likert_rejects_scalar_columns(full_survey):
    response = Response.objects.create(survey=full_survey["survey"])
    choice = full_survey["likert"].choices.first()
    answer = Answer(
        response=response,
        question=full_survey["likert"],
        choice=choice,
        text_value="extra",
    )
    with pytest.raises(ValidationError) as exc:
        answer.full_clean()
    assert "choice" in exc.value.error_dict


# --- runners.py ---


@pytest.mark.django_db
def test_progress_percent_branching_gap_with_zero_answers(branching_survey):
    survey, _q1, q2, _q3, _remote = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)
    # step 2, no answers yet: gap=0 (linear), uses by_order branch
    percent = runner.progress_percent(q2.order)
    assert percent == min(99, int(q2.order / runner.total_questions() * 100))


@pytest.mark.django_db
def test_progress_percent_branching_gap_with_one_answer(branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": remote})
    runner = SurveyRunner(survey, response)
    percent = runner.progress_percent(q3.order)
    assert percent >= 75


@pytest.mark.django_db
def test_progress_percent_preview_mode_uses_step_minus_one(branching_survey):
    survey, *_ = branching_survey
    runner = SurveyRunner(
        survey, Response(survey=survey, current_step=2), record=False
    )
    assert runner.progress_percent(2) >= 1


@pytest.mark.django_db
def test_start_survey_404_when_no_questions(client):
    survey = Survey.objects.create(
        title="Empty", slug="empty-published", is_published=True
    )
    response = client.post(reverse("surveys:start", args=[survey.slug]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_step_redirects_when_order_not_on_path(client, branching_survey):
    survey, q1, q2, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    response = client.get(reverse("surveys:step", args=[survey.slug, q2.order]))
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:step", args=[survey.slug, q1.order]))


@pytest.mark.django_db
def test_step_404_when_path_order_has_no_question(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    response = survey.responses.get()
    response.current_step = 99
    response.save(update_fields=["current_step"])
    session = client.session
    session[f"survey_path_{survey.id}"] = [99]
    session.save()
    result = client.get(reverse("surveys:step", args=[survey.slug, 99]))
    assert result.status_code == 404


@pytest.mark.django_db
def test_step_back_without_session_redirects_to_intro(client, branching_survey):
    survey, q1, *_ = branching_survey
    response = client.get(reverse("surveys:step_back", args=[survey.slug, q1.order]))
    assert response.status_code == 302
    assert reverse("surveys:intro", args=[survey.slug]) in response["Location"]


@pytest.mark.django_db
def test_step_back_wrong_step_redirects_to_current(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": remote.id})
    response = client.get(reverse("surveys:step_back", args=[survey.slug, q1.order]))
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:step", args=[survey.slug, q3.order]))


@pytest.mark.django_db
def test_preview_404_for_unknown_slug(staff_user, client):
    client.force_login(staff_user)
    response = client.get(reverse("surveys:preview", args=["no-such-slug"]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_preview_404_when_survey_has_no_questions(staff_user, client):
    survey = Survey.objects.create(title="Blank", slug="blank-preview", is_published=False)
    client.force_login(staff_user)
    response = client.get(reverse("surveys:preview", args=[survey.slug]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_preview_step_redirects_when_step_not_on_path(client, branching_survey, staff_user):
    survey, q1, q2, q3, remote = branching_survey
    client.force_login(staff_user)
    client.get(reverse("surveys:preview", args=[survey.slug]))
    response = client.get(reverse("surveys:preview_step", args=[survey.slug, q3.order]))
    assert response.status_code == 302
    assert response["Location"].endswith(
        reverse("surveys:preview_step", args=[survey.slug, q1.order])
    )


@pytest.mark.django_db
def test_preview_step_back_navigation(client, branching_survey, staff_user):
    survey, q1, _q2, q3, remote = branching_survey
    client.force_login(staff_user)
    client.get(reverse("surveys:preview", args=[survey.slug]))
    client.post(
        reverse("surveys:preview_step", args=[survey.slug, 1]),
        {"value": remote.id},
    )
    response = client.get(
        reverse("surveys:preview_step_back", args=[survey.slug, q3.order])
    )
    assert response.status_code == 302
    assert response["Location"].endswith(
        reverse("surveys:preview_step", args=[survey.slug, q1.order])
    )

    response = client.get(
        reverse("surveys:preview_step_back", args=[survey.slug, q1.order])
    )
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:preview", args=[survey.slug]))


@pytest.mark.django_db
def test_preview_step_back_from_first_step_goes_to_preview(client, branching_survey, staff_user):
    survey, q1, _q2, q3, remote = branching_survey
    client.force_login(staff_user)
    client.get(reverse("surveys:preview", args=[survey.slug]))
    client.post(
        reverse("surveys:preview_step", args=[survey.slug, 1]),
        {"value": remote.id},
    )
    client.get(reverse("surveys:preview_step", args=[survey.slug, q1.order]))
    response = client.get(
        reverse("surveys:preview_step_back", args=[survey.slug, q1.order])
    )
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:preview", args=[survey.slug]))


@pytest.mark.django_db
def test_preview_step_back_404_for_unknown_slug(staff_user, client):
    client.force_login(staff_user)
    response = client.get(reverse("surveys:preview_step_back", args=["missing", 1]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_ensure_path_rebuilds_from_answers(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": remote.id})
    session = client.session
    session.pop(f"survey_path_{survey.id}", None)
    session.save()
    response = client.get(reverse("surveys:step", args=[survey.slug, q3.order]))
    assert response.status_code == 200


@pytest.mark.django_db
def test_record_forward_appends_when_path_tail_mismatches(branching_survey):
    from apps.surveys.views import _record_forward

    survey, q1, q2, q3, remote = branching_survey
    factory = RequestFactory()
    request = factory.get("/")
    request.session = {}
    _record_forward(request, survey, q1.order, q3.order, preview=False)
    assert request.session[f"survey_path_{survey.id}"] == [q1.order, q3.order]

    request.session[f"survey_path_{survey.id}"] = [q1.order]
    _record_forward(request, survey, q2.order, q3.order, preview=False)
    assert request.session[f"survey_path_{survey.id}"] == [q1.order, q2.order, q3.order]

    request.session[f"survey_path_{survey.id}"] = [q1.order]
    _record_forward(request, survey, q3.order, q3.order, preview=False)
    assert request.session[f"survey_path_{survey.id}"] == [q1.order]


@pytest.mark.django_db
def test_rebuild_path_returns_empty_when_no_questions(branching_survey):
    from apps.surveys.views import _rebuild_path_from_response

    survey, *_ = branching_survey
    survey.questions.all().delete()
    response = Response.objects.create(survey=survey, current_step=1)
    assert _rebuild_path_from_response(survey, response) == []


@pytest.mark.django_db
def test_rebuild_path_when_current_step_past_branch_end(branching_survey):
    from apps.surveys.views import _rebuild_path_from_response

    survey, q1, _q2, _q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    ResponseRepository.save_answer(response, q1, {"value": remote})
    response.current_step = 99
    response.save(update_fields=["current_step"])
    assert _rebuild_path_from_response(survey, response) == [q1.order, _q3.order]


@pytest.mark.django_db
def test_start_resumes_in_progress_without_force_new(client, branching_survey):
    survey, q1, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    survey_response = survey.responses.get()
    survey_response.current_step = q1.order
    survey_response.save(update_fields=["current_step"])
    response = client.post(reverse("surveys:start", args=[survey.slug]))
    assert response.status_code == 302
    assert response["Location"].endswith(
        reverse("surveys:step", args=[survey.slug, q1.order])
    )

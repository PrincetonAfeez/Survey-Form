"""Baseline accessibility markup and form wiring"""

import pytest
from apps.surveys.forms import _apply_accessibility_attrs, _error_list_id, form_for_question
from django.urls import reverse


@pytest.mark.django_db
def test_step_validation_includes_aria_attrs(client, branching_survey):
    survey, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    response = client.post(
        reverse("surveys:step", args=[survey.slug, 1]),
        {},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 422
    content = response.content
    assert b'aria-invalid="true"' in content
    assert b"aria-describedby=" in content
    assert b'role="alert"' in content
    assert b"id_value-errors" in content
    assert b'id="question-label"' in content


@pytest.mark.django_db
def test_intro_page_has_skip_link(client, branching_survey):
    survey, *_ = branching_survey
    response = client.get(reverse("surveys:intro", args=[survey.slug]))
    assert b"Skip to main content" in response.content
    assert b'id="main-content"' in response.content


@pytest.mark.django_db
def test_apply_accessibility_attrs_only_when_invalid(full_survey):
    valid = form_for_question(full_survey["short"], data={"value": "ok"})
    assert "aria-invalid" not in valid.fields["value"].widget.attrs

    invalid = form_for_question(full_survey["short"], data={"value": ""})
    assert invalid.fields["value"].widget.attrs["aria-invalid"] == "true"
    assert invalid.fields["value"].widget.attrs["aria-describedby"] == _error_list_id(
        invalid["value"].auto_id
    )


@pytest.mark.django_db
def test_apply_accessibility_attrs_noop_when_unbound(full_survey):
    form = form_for_question(full_survey["short"])
    _apply_accessibility_attrs(form)
    assert "aria-invalid" not in form.fields["value"].widget.attrs

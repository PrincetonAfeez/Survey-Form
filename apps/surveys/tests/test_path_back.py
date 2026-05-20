""" Unit tests for session path helpers used by back navigation """

import pytest
from apps.surveys.views import (
    _can_step_back,
    _path_step_back,
    _record_forward,
    _truncate_path_to_step,
)


@pytest.mark.django_db
def test_truncate_path_to_step_drops_stale_tail(branching_survey):
    survey, q1, q2, q3, _ = branching_survey
    path = [q1.id, q2.id, q3.id]
    assert _truncate_path_to_step(survey, path, q2.order) == [q1.id, q2.id]
    assert _truncate_path_to_step(survey, path, q1.order) == [q1.id]
    assert _truncate_path_to_step(survey, path, 99) == path


@pytest.mark.django_db
def test_path_step_back_returns_previous_and_shortened_path(branching_survey):
    survey, q1, q2, q3, _ = branching_survey
    path = [q1.id, q2.id, q3.id]
    previous, new_path = _path_step_back(survey, path, q2.order)
    assert previous == q1.order
    assert new_path == [q1.id]


@pytest.mark.django_db
def test_path_step_back_on_first_step_returns_none(branching_survey):
    survey, q1, q2, q3, _ = branching_survey
    path = [q1.id, q2.id, q3.id]
    previous, new_path = _path_step_back(survey, path, q1.order)
    assert previous is None
    assert new_path == [q1.id]


@pytest.mark.django_db
def test_record_forward_same_question_is_noop(branching_survey):
    survey, q1, _q2, q3, _ = branching_survey
    factory_request = type("R", (), {"session": {}})()
    _record_forward(factory_request, survey, q3, q3, preview=False)
    assert factory_request.session == {}
    factory_request.session[f"survey_path_{survey.id}"] = [q1.id, q3.id]
    _record_forward(factory_request, survey, q3, q3, preview=False)
    assert factory_request.session[f"survey_path_{survey.id}"] == [q1.id, q3.id]


@pytest.mark.django_db
def test_can_step_back_requires_prior_entry_in_path(branching_survey):
    survey, q1, q2, q3, _ = branching_survey
    path = [q1.id, q2.id, q3.id]
    assert _can_step_back(survey, path, q2.order) is True
    assert _can_step_back(survey, path, q1.order) is False
    assert _can_step_back(survey, path, 99) is False

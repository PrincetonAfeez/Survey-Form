"""Unit tests for session path helpers used by back navigation."""

from apps.surveys.views import (
    _can_step_back,
    _path_step_back,
    _truncate_path_to_step,
)


def test_truncate_path_to_step_drops_stale_tail():
    assert _truncate_path_to_step([1, 2, 3], 2) == [1, 2]
    assert _truncate_path_to_step([1, 3], 1) == [1]
    assert _truncate_path_to_step([1, 2], 99) == [1, 2]


def test_path_step_back_returns_previous_and_shortened_path():
    previous, new_path = _path_step_back([1, 2, 3], 2)
    assert previous == 1
    assert new_path == [1]


def test_path_step_back_on_first_step_returns_none():
    previous, new_path = _path_step_back([1, 2, 3], 1)
    assert previous is None
    assert new_path == [1]


def test_record_forward_same_order_is_noop():
    from apps.surveys.views import _record_forward

    class FakeSurvey:
        id = 1

    survey = FakeSurvey()
    request = type("R", (), {"session": {}})()
    request.session = {}
    _record_forward(request, survey, 3, 3, preview=False)
    assert request.session == {}
    request.session["survey_path_1"] = [1, 3]
    _record_forward(request, survey, 3, 3, preview=False)
    assert request.session["survey_path_1"] == [1, 3]


def test_can_step_back_requires_prior_entry_in_path():
    assert _can_step_back([1, 2, 3], 2) is True
    assert _can_step_back([1, 2, 3], 1) is False
    assert _can_step_back([1, 2, 3], 99) is False

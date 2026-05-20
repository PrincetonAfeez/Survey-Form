import pytest
from django.urls import resolve, reverse


@pytest.mark.parametrize(
    "name,kwargs,view_name",
    [
        ("surveys:list", {}, "survey_list"),
        ("surveys:intro", {"slug": "demo"}, "survey_intro"),
        ("surveys:start", {"slug": "demo"}, "start_survey"),
        ("surveys:step", {"slug": "demo", "step": 1}, "step"),
        ("surveys:step_back", {"slug": "demo", "step": 1}, "step_back"),
        ("surveys:resume", {"slug": "demo", "token": "tok"}, "resume"),
        ("surveys:done", {"slug": "demo"}, "done"),
        ("surveys:preview", {"slug": "demo"}, "preview"),
        ("surveys:preview_step", {"slug": "demo", "step": 2}, "preview_step"),
        ("surveys:preview_step_back", {"slug": "demo", "step": 2}, "preview_step_back"),
        ("surveys:results", {"survey_id": 1}, "results_dashboard"),
        ("surveys:results_raw", {"survey_id": 1}, "results_raw"),
        ("surveys:export_csv", {"survey_id": 1}, "export_csv"),
        ("surveys:export_json", {"survey_id": 1}, "export_json"),
    ],
)
def test_url_reverse_and_resolve(name, kwargs, view_name):
    path = reverse(name, kwargs=kwargs)
    match = resolve(path)
    assert match.func.__name__ == view_name

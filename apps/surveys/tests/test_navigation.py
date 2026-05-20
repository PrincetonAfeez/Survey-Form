"""Back navigation, Finish/Next label, and path session behavior."""

import pytest
from apps.surveys.repositories import ResponseRepository
from apps.surveys.runners import SurveyRunner
from django.urls import reverse


@pytest.mark.django_db
def test_back_returns_to_previous_question(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": remote.id})

    response = client.get(reverse("surveys:step_back", args=[survey.slug, q3.order]))
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:step", args=[survey.slug, q1.order]))

    page = client.get(reverse("surveys:step", args=[survey.slug, q1.order]))
    assert page.status_code == 200
    assert b"Work style" in page.content


@pytest.mark.django_db
def test_back_on_first_question_goes_to_intro(client, branching_survey):
    survey, q1, *_ = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    response = client.get(reverse("surveys:step_back", args=[survey.slug, q1.order]))
    assert response.status_code == 302
    assert reverse("surveys:intro", args=[survey.slug]) in response["Location"]


@pytest.mark.django_db
def test_browser_back_to_prior_step_in_path(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": remote.id})

    response = client.get(reverse("surveys:step", args=[survey.slug, q1.order]))
    assert response.status_code == 200
    assert b"Work style" in response.content


@pytest.mark.django_db
def test_on_page_back_after_browser_back_one_click_per_step(client, branching_survey):
    """Browser Back desyncs path tail; on-page Back must use path.index(current_step)."""
    survey, q1, _q2, q3, remote = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": remote.id})
    assert client.session[f"survey_path_{survey.id}"] == [q1.order, q3.order]

    client.get(reverse("surveys:step", args=[survey.slug, q1.order]))
    assert client.session[f"survey_path_{survey.id}"] == [q1.order]

    response = client.get(reverse("surveys:step_back", args=[survey.slug, q1.order]))
    assert response.status_code == 302
    assert reverse("surveys:intro", args=[survey.slug]) in response["Location"]


@pytest.mark.django_db
def test_on_page_back_from_step_two_after_browser_back(client, branching_survey):
    survey, q1, q2, q3, remote = branching_survey
    office = q1.choices.get(label="Office")
    client.post(reverse("surveys:start", args=[survey.slug]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": office.id})
    client.post(reverse("surveys:step", args=[survey.slug, 2]), {"value": "15"})
    assert client.session[f"survey_path_{survey.id}"] == [1, 2, 3]

    client.get(reverse("surveys:step", args=[survey.slug, q2.order]))
    assert client.session[f"survey_path_{survey.id}"] == [1, 2]

    response = client.get(reverse("surveys:step_back", args=[survey.slug, q2.order]))
    assert response.status_code == 302
    assert response["Location"].endswith(reverse("surveys:step", args=[survey.slug, q1.order]))


@pytest.mark.django_db
def test_can_go_back_false_on_first_step_when_path_stale(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": remote.id})

    page = client.get(reverse("surveys:step", args=[survey.slug, q1.order]))
    back_link = reverse("surveys:step_back", args=[survey.slug, q1.order]).encode()
    assert b'href="' not in page.content or back_link not in page.content
    assert b"Back</a>" not in page.content


@pytest.mark.django_db
def test_finish_label_on_branching_final_question(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    client.post(reverse("surveys:start", args=[survey.slug]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": remote.id})

    page = client.get(reverse("surveys:step", args=[survey.slug, q3.order]))
    assert b"Finish" in page.content
    assert b">Next<" not in page.content or page.content.count(b"Next") == 0


@pytest.mark.django_db
def test_next_label_on_non_final_question(client, branching_survey):
    survey, q1, _q2, _q3, remote = branching_survey
    office = q1.choices.get(label="Office")
    client.post(reverse("surveys:start", args=[survey.slug]))

    page = client.get(reverse("surveys:step", args=[survey.slug, 1]))
    assert b"Next" in page.content

    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": office.id})
    page = client.get(reverse("surveys:step", args=[survey.slug, 2]))
    assert b"Next" in page.content


@pytest.mark.django_db
def test_runner_is_final_step_uses_saved_branch_answer(branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)
    ResponseRepository.save_answer(response, q1, {"value": remote})

    assert runner.is_final_step(q3) is True
    assert runner.is_final_step(q1) is False


@pytest.mark.django_db
def test_path_truncates_when_rebranching(client, branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    office = q1.choices.get(label="Office")
    client.post(reverse("surveys:start", args=[survey.slug]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": remote.id})
    client.get(reverse("surveys:step_back", args=[survey.slug, q3.order]))
    client.post(reverse("surveys:step", args=[survey.slug, 1]), {"value": office.id})

    response = client.get(reverse("surveys:step", args=[survey.slug, 2]))
    assert response.status_code == 200
    assert b"Commute" in response.content

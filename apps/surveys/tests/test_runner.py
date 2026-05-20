import pytest
from apps.surveys.models import Answer, Response, Survey
from apps.surveys.repositories import ResponseRepository
from apps.surveys.runners import SubmitResult, SurveyRunner


@pytest.mark.django_db
def test_submit_result_properties(branching_survey):
    survey, q1, *_ = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)
    result = runner.submit({"value": ""}, step=1)

    assert result.ok is False
    assert result.errors
    assert result.next_step is None
    assert result.is_final is False


@pytest.mark.django_db
def test_runner_uses_branch_rule(branching_survey):
    survey, _q1, _q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)

    result = runner.submit({"value": str(remote.id)}, step=1)

    response.refresh_from_db()
    assert result.ok is True
    assert result.next_question == q3
    assert result.next_step == q3.order
    assert response.current_step == 3
    assert Answer.objects.filter(response=response, question__order=1, choice=remote).exists()


@pytest.mark.django_db
def test_runner_falls_back_to_next_order(branching_survey):
    survey, _q1, q2, _q3, remote = branching_survey
    office = remote.question.choices.get(label="Office")
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)

    result = runner.submit({"value": str(office.id)}, step=1)

    assert result.next_question == q2


@pytest.mark.django_db
def test_submit_rolls_back_when_step_update_fails(branching_survey, monkeypatch):
    survey, q1, _q2, _q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)

    def fail_move(*_args, **_kwargs):
        raise RuntimeError("simulated failure after save")

    monkeypatch.setattr(ResponseRepository, "move_to_step", fail_move)
    with pytest.raises(RuntimeError, match="simulated failure"):
        runner.submit({"value": str(remote.id)}, step=1)

    assert not response.answers.filter(question=q1).exists()


@pytest.mark.django_db
def test_submit_rolls_back_completion_when_prune_fails(branching_survey, monkeypatch):
    survey, q1, _q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)
    runner.submit({"value": str(remote.id)}, step=1)

    def fail_prune(*_args, **_kwargs):
        raise RuntimeError("simulated prune failure")

    monkeypatch.setattr(runner, "_discard_off_route_answers", fail_prune)
    rating = q3.choices.get(label="4")
    with pytest.raises(RuntimeError, match="simulated prune"):
        runner.submit({"value": str(rating.id)}, step=q3.order)

    response.refresh_from_db()
    assert response.is_complete is False
    assert response.completed_at is None


@pytest.mark.django_db
def test_runner_submit_invalid_returns_early(branching_survey):
    survey, *_ = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)
    before = response.answers.count()
    result = runner.submit({}, step=1)
    assert result.ok is False
    assert response.answers.count() == before


@pytest.mark.django_db
def test_runner_submit_missing_question_raises(branching_survey):
    survey, *_ = branching_survey
    runner = SurveyRunner(survey, ResponseRepository.start(survey))
    with pytest.raises(ValueError, match="missing question"):
        runner.submit({"value": "x"}, step=999)


@pytest.mark.django_db
def test_runner_completes_on_last_question(branching_survey):
    survey, q1, _q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)
    runner.submit({"value": str(remote.id)}, step=1)
    rating = q3.choices.get(label="4")
    result = runner.submit({"value": str(rating.id)}, step=q3.order)

    response.refresh_from_db()
    assert result.is_final is True
    assert response.is_complete


@pytest.mark.django_db
def test_runner_preview_mode_does_not_persist(branching_survey):
    survey, q1, _q2, _q3, remote = branching_survey
    response = Response(survey=survey, current_step=1)
    runner = SurveyRunner(survey, response, record=False)
    result = runner.submit({"value": str(remote.id)}, step=1)

    assert result.ok is True
    assert survey.responses.count() == 0


@pytest.mark.django_db
def test_runner_current_question_and_step_number(branching_survey):
    survey, q1, *_ = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)
    assert runner.current_question() == q1
    assert runner.step_number() == 1
    assert runner.total_questions() == 3


@pytest.mark.django_db
def test_runner_form_for_loads_saved_answer(branching_survey):
    survey, q1, q2, _q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)
    office = q1.choices.get(label="Office")
    runner.submit({"value": str(office.id)}, step=1)
    runner.submit({"value": "12"}, step=2)

    form = runner.form_for(q2)
    assert form.is_bound is False
    assert form.fields["value"].initial == 12 or str(form.fields["value"].initial) == "12"


@pytest.mark.django_db
def test_runner_next_question_non_branching(full_survey):
    survey = full_survey["survey"]
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)
    nxt = runner.next_question(full_survey["short"], None)
    assert nxt == full_survey["long"]


@pytest.mark.django_db
def test_runner_branch_choice_only_for_single(full_survey):
    assert SurveyRunner._branch_choice(full_survey["short"], {"value": "x"}) is None


@pytest.mark.django_db
def test_runner_is_complete_reflects_response(branching_survey):
    survey, *_ = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)
    assert runner.is_complete() is False
    ResponseRepository.complete(response)
    response.refresh_from_db()
    assert runner.is_complete() is True


@pytest.mark.django_db
def test_progress_percent_edge_cases(branching_survey):
    survey, q1, q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)

    assert runner.progress_percent(1) >= 1
    assert runner.progress_percent(q3.order) >= 75
    ResponseRepository.save_answer(response, q1, {"value": remote})
    assert runner.progress_percent(q3.order) >= 75

    empty = Survey.objects.create(title="Empty", slug="empty-runner")
    empty_runner = SurveyRunner(empty, Response(survey=empty, current_step=1), record=False)
    assert empty_runner.progress_percent(1) == 0

    last_order = survey.questions.order_by("-order").first().order
    assert runner.progress_percent(last_order) == 100


@pytest.mark.django_db
def test_progress_percent_accounts_for_branching(branching_survey):
    survey, _q1, _q2, q3, remote = branching_survey
    response = ResponseRepository.start(survey)
    runner = SurveyRunner(survey, response)
    ResponseRepository.save_answer(response, remote.question, {"value": remote})

    assert runner.progress_percent(q3.order) >= 75


@pytest.mark.django_db
def test_submit_result_is_frozen_dataclass(branching_survey):
    from dataclasses import FrozenInstanceError

    survey, *_ = branching_survey
    runner = SurveyRunner(survey, ResponseRepository.start(survey))
    bad = runner.submit({}, step=1)
    assert isinstance(bad, SubmitResult)
    with pytest.raises(FrozenInstanceError):
        bad.ok = True  # type: ignore[misc]

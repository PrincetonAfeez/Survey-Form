from __future__ import annotations

import csv
import json

from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .aggregators import aggregate_survey, response_metrics
from .display import format_answer_value
from .models import Question, Response
from .pathing import build_path_from_response
from .repositories import ResponseRepository, SurveyRepository
from .runners import SurveyRunner
from .tokens import issue_resume_token, verify_resume_token


def survey_list(request):
    surveys = SurveyRepository.get_published()
    return render(request, "surveys/survey_list.html", {"surveys": surveys})


def survey_intro(request, slug: str):
    survey = _published_survey_or_404(slug)
    existing_response = _response_from_session(request, survey)
    return render(
        request,
        "surveys/survey_intro.html",
        {"survey": survey, "existing_response": existing_response},
    )


@require_POST
def start_survey(request, slug: str):
    survey = _published_survey_or_404(slug)
    force_new = request.POST.get("force_new") == "1"

    if not force_new:
        existing = _response_from_session(request, survey)
        if existing is not None and not existing.is_complete:
            return redirect(
                "surveys:step", slug=survey.slug, step=existing.current_step
            )

    try:
        response = ResponseRepository.start(survey)
    except ValueError as exc:
        raise Http404(str(exc)) from exc
    request.session[_session_key(survey)] = str(response.uuid)
    _init_path(request, survey, response.current_step)
    return redirect("surveys:step", slug=survey.slug, step=response.current_step)


def step(request, slug: str, step: int):
    survey = _published_survey_or_404(slug)
    response = _response_from_session(request, survey)
    if response is None:
        return redirect("surveys:intro", slug=survey.slug)

    if response.is_complete:
        return redirect("surveys:done", slug=survey.slug)

    question = SurveyRepository.get_question_by_order(survey, step)
    if question is None:
        raise Http404("Question not found.")

    path = _ensure_path(request, survey, response)
    if step not in path:
        return redirect("surveys:step", slug=survey.slug, step=response.current_step)
    path = _truncate_path_to_step(path, step)
    _set_path(request, survey, path)
    if step != response.current_step:
        ResponseRepository.move_to_step(response, step)

    runner = SurveyRunner(survey, response)

    if request.method == "POST":
        result = runner.submit(request.POST, step=step)
        if not result.ok:
            return _render_step(
                request, runner, question, result.form, step, status=422, preview=False
            )
        return _after_successful_submit(request, runner, result, preview=False)

    form = runner.form_for(question)
    return _render_step(request, runner, question, form, step, preview=False)


def step_back(request, slug: str, step: int):
    survey = _published_survey_or_404(slug)
    response = _response_from_session(request, survey)
    if response is None:
        return redirect("surveys:intro", slug=survey.slug)

    path = _ensure_path(request, survey, response)
    if step != response.current_step:
        return redirect("surveys:step", slug=survey.slug, step=response.current_step)

    previous, new_path = _path_step_back(path, step)
    if previous is None:
        return redirect("surveys:intro", slug=survey.slug)

    _set_path(request, survey, new_path)
    ResponseRepository.move_to_step(response, previous)
    return redirect("surveys:step", slug=survey.slug, step=previous)


def resume(request, slug: str, token: str):
    survey = _published_survey_or_404(slug)
    payload = verify_resume_token(token)
    if not payload or payload.get("s") != survey.id:
        return render(request, "surveys/resume_invalid.html", {"survey": survey}, status=400)

    response = ResponseRepository.for_respondent(payload.get("r"))
    if response is None or response.survey_id != survey.id:
        return render(request, "surveys/resume_invalid.html", {"survey": survey}, status=400)

    request.session[_session_key(survey)] = str(response.uuid)
    _set_path(request, survey, _rebuild_path_from_response(survey, response))
    if response.is_complete:
        return redirect("surveys:done", slug=survey.slug)
    return redirect("surveys:step", slug=survey.slug, step=response.current_step)


def done(request, slug: str):
    survey = _published_survey_or_404(slug)
    response = _response_from_session(request, survey)
    if response is None or not response.is_complete:
        return redirect("surveys:intro", slug=survey.slug)
    return render(request, "surveys/done.html", {"survey": survey, "response": response})


@staff_member_required
def preview(request, slug: str):
    survey = SurveyRepository.get_for_preview(slug, request.user)
    if survey is None:
        raise Http404("Survey not found.")
    first_order = SurveyRepository.first_question_order(survey)
    if first_order is None:
        raise Http404("Survey has no questions.")
    _init_path(request, survey, first_order, preview=True)
    return redirect("surveys:preview_step", slug=slug, step=first_order)


@staff_member_required
def preview_step(request, slug: str, step: int):
    survey = SurveyRepository.get_for_preview(slug, request.user)
    if survey is None:
        raise Http404("Survey not found.")

    path = _get_path(request, survey, preview=True)
    if not path:
        _init_path(request, survey, step, preview=True)
        path = _get_path(request, survey, preview=True)
    if step not in path:
        return redirect("surveys:preview_step", slug=survey.slug, step=path[-1])

    path = _truncate_path_to_step(path, step)
    _set_path(request, survey, path, preview=True)

    response = Response(survey=survey, current_step=step)
    runner = SurveyRunner(survey, response, record=False)
    question = runner.question_for_step(step)
    if question is None:
        return redirect("surveys:preview", slug=survey.slug)

    if request.method == "POST":
        result = runner.submit(request.POST, step=step)
        if not result.ok:
            return _render_step(
                request, runner, question, result.form, step, status=422, preview=True
            )
        return _after_successful_submit(request, runner, result, preview=True)

    form = runner.form_for(question)
    return _render_step(request, runner, question, form, step, preview=True)


@staff_member_required
def preview_step_back(request, slug: str, step: int):
    survey = SurveyRepository.get_for_preview(slug, request.user)
    if survey is None:
        raise Http404("Survey not found.")

    path = _get_path(request, survey, preview=True)
    path = _truncate_path_to_step(path, step)

    previous, new_path = _path_step_back(path, step)
    if previous is None:
        return redirect("surveys:preview", slug=survey.slug)

    _set_path(request, survey, new_path, preview=True)
    return redirect("surveys:preview_step", slug=survey.slug, step=previous)


@staff_member_required
def results_dashboard(request, survey_id: int):
    survey = SurveyRepository.get_for_results(survey_id, request.user)
    if survey is None:
        raise Http404("Survey not found.")
    return render(
        request,
        "surveys/results_dashboard.html",
        {
            "survey": survey,
            "aggregates": aggregate_survey(survey),
            "metrics": response_metrics(survey),
        },
    )


@staff_member_required
def results_raw(request, survey_id: int):
    survey = SurveyRepository.get_for_results(survey_id, request.user)
    if survey is None:
        raise Http404("Survey not found.")

    queryset = ResponseRepository.list_for_survey(survey)
    query = request.GET.get("q", "").strip()
    if query:
        queryset = ResponseRepository.filter_by_answer_query(queryset, query)

    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    template = (
        "surveys/partials/_raw_table.html" if _is_htmx(request) else "surveys/results_raw.html"
    )
    return render(request, template, {"survey": survey, "page": page, "query": query})


@staff_member_required
def export_csv(request, survey_id: int):
    survey = SurveyRepository.get_for_results(survey_id, request.user)
    if survey is None:
        raise Http404("Survey not found.")

    questions = list(SurveyRepository.questions_for_survey(survey))
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{survey.slug}-responses.csv"'
    writer = csv.writer(response)
    writer.writerow(["response_uuid", "started_at", "completed_at", *[q.text for q in questions]])

    for survey_response in ResponseRepository.list_for_survey(survey, complete_only=True):
        answers = {answer.question_id: answer for answer in survey_response.answers.all()}
        writer.writerow(
            [
                survey_response.uuid,
                survey_response.started_at,
                survey_response.completed_at,
                *[format_answer_value(answers.get(question.id)) for question in questions],
            ]
        )
    return response


@staff_member_required
def export_json(request, survey_id: int):
    survey = SurveyRepository.get_for_results(survey_id, request.user)
    if survey is None:
        raise Http404("Survey not found.")

    data = []
    for survey_response in ResponseRepository.list_for_survey(survey, complete_only=True):
        data.append(
            {
                "response": {
                    "uuid": survey_response.uuid,
                    "started_at": survey_response.started_at,
                    "completed_at": survey_response.completed_at,
                },
                "answers": [
                    {
                        "question": answer.question.text,
                        "type": answer.question.type,
                        "value": format_answer_value(answer),
                    }
                    for answer in survey_response.answers.all()
                ],
            }
        )

    return HttpResponse(
        json.dumps(data, cls=DjangoJSONEncoder, indent=2),
        content_type="application/json",
    )


def _render_step(
    request,
    runner: SurveyRunner,
    question: Question,
    form,
    step: int,
    *,
    status: int = 200,
    preview: bool,
):
    context = _step_context(request, runner, question, form, step, preview=preview)
    template = "surveys/partials/_wizard.html" if _is_htmx(request) else "surveys/step.html"
    return render(request, template, context, status=status)


def _after_successful_submit(request, runner: SurveyRunner, result, *, preview: bool):
    if result.is_final:
        url = (
            reverse("surveys:preview", args=[runner.survey.slug])
            if preview
            else reverse("surveys:done", args=[runner.survey.slug])
        )
        if _is_htmx(request):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = url
            return response
        return redirect(url)

    next_step = result.next_step
    _record_forward(
        request,
        runner.survey,
        result.question.order,
        next_step,
        preview=preview,
    )
    url = (
        reverse("surveys:preview_step", args=[runner.survey.slug, next_step])
        if preview
        else reverse("surveys:step", args=[runner.survey.slug, next_step])
    )

    if not _is_htmx(request):
        return redirect(url)

    next_question = result.next_question
    next_form = runner.form_for(next_question)
    context = _step_context(request, runner, next_question, next_form, next_step, preview=preview)
    response = render(request, "surveys/partials/_wizard.html", context)
    response["HX-Push-Url"] = url
    response["HX-Trigger"] = json.dumps({"draftSaved": "Saved"})
    return response


def _step_context(
    request, runner: SurveyRunner, question: Question, form, step: int, *, preview: bool
):
    total = runner.total_questions()
    action_name = "surveys:preview_step" if preview else "surveys:step"
    action_url = reverse(action_name, args=[runner.survey.slug, step])
    resume_url = None
    if not preview and runner.response.pk:
        token = issue_resume_token(runner.response)
        resume_url = request.build_absolute_uri(
            reverse("surveys:resume", args=[runner.survey.slug, token])
        )
    progress_percent = runner.progress_percent(step)
    path = _get_path(request, runner.survey, preview=preview)
    can_go_back = _can_step_back(path, step)
    back_url = None
    if can_go_back:
        back_name = "surveys:preview_step_back" if preview else "surveys:step_back"
        back_url = reverse(back_name, args=[runner.survey.slug, step])
    return {
        "survey": runner.survey,
        "runner": runner,
        "question": question,
        "form": form,
        "step": step,
        "total": total,
        "progress_percent": progress_percent,
        "action_url": action_url,
        "resume_url": resume_url,
        "preview": preview,
        "is_final_step": runner.is_final_step(question),
        "can_go_back": can_go_back,
        "back_url": back_url,
    }


def _published_survey_or_404(slug: str):
    survey = SurveyRepository.get_by_slug(slug)
    if survey is None:
        raise Http404("Survey not found.")
    return survey


def _session_key(survey) -> str:
    return f"survey_response_{survey.id}"


def _response_from_session(request, survey):
    uuid = request.session.get(_session_key(survey))
    if not uuid:
        return None
    response = ResponseRepository.for_respondent(uuid)
    if response is None or response.survey_id != survey.id:
        request.session.pop(_session_key(survey), None)
        return None
    return response


def _is_htmx(request) -> bool:
    return bool(getattr(request, "htmx", False))


def _path_key(survey, *, preview: bool = False) -> str:
    prefix = "survey_preview_path" if preview else "survey_path"
    return f"{prefix}_{survey.id}"


def _get_path(request, survey, *, preview: bool = False) -> list[int]:
    return list(request.session.get(_path_key(survey, preview=preview), []))


def _truncate_path_to_step(path: list[int], step: int) -> list[int]:
    """Drop tail orders after step when the user navigates backward (e.g. browser Back)."""
    if step not in path:
        return path
    return path[: path.index(step) + 1]


def _can_step_back(path: list[int], step: int) -> bool:
    if step not in path:
        return False
    return path.index(step) > 0


def _path_step_back(path: list[int], current_step: int) -> tuple[int | None, list[int]]:
    """
    Given path synced to current_step, return (previous_order, new_path) or (None, path).
    new_path ends at previous_order (current_step removed).
    """
    path = _truncate_path_to_step(path, current_step)
    if not _can_step_back(path, current_step):
        return None, path
    idx = path.index(current_step)
    previous = path[idx - 1]
    return previous, path[:idx]


def _set_path(request, survey, path: list[int], *, preview: bool = False) -> None:
    request.session[_path_key(survey, preview=preview)] = path


def _init_path(request, survey, first_order: int, *, preview: bool = False) -> None:
    _set_path(request, survey, [first_order], preview=preview)


def _record_forward(
    request, survey, from_order: int, to_order: int, *, preview: bool = False
) -> None:
    if from_order == to_order:
        return
    path = _get_path(request, survey, preview=preview)
    if from_order in path:
        path = path[: path.index(from_order) + 1]
    elif not path:
        path = [from_order]
    elif path[-1] != from_order:
        path.append(from_order)
    path.append(to_order)
    _set_path(request, survey, path, preview=preview)


def _rebuild_path_from_response(survey, response: Response) -> list[int]:
    return build_path_from_response(survey, response)


def _ensure_path(request, survey, response: Response) -> list[int]:
    path = _get_path(request, survey)
    if not path:
        path = _rebuild_path_from_response(survey, response)
        _set_path(request, survey, path)
    return path

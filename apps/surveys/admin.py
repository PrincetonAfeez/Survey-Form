""" Admin for surveys app """

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from .models import Answer, BranchRule, Choice, Question, Response, Survey


def _format_validation_error(exc: ValidationError) -> str:
    if hasattr(exc, "error_dict"):
        parts = []
        for field, errs in exc.error_dict.items():
            label = "Survey" if field in (None, "__all__") else str(field)
            for err in errs:
                parts.append(f"{label}: {err}")
        return " ".join(parts) if parts else str(exc)
    if hasattr(exc, "messages"):
        try:
            return " ".join(str(m) for m in exc.messages)
        except AttributeError:
            pass
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message:
        return message
    try:
        error_list = list(exc.error_list)
    except AttributeError:
        error_list = None
    if error_list is not None and len(error_list) == 1 and isinstance(error_list[0], str):
        return error_list[0]
    args = getattr(exc, "args", ())
    if len(args) == 1 and isinstance(args[0], str):
        return args[0]
    return str(exc)


class ValidateAfterSaveMixin:
    """Run model full_clean() after inlines save; surface errors in admin instead of 500."""

    def response_add(self, request, obj, post_url_continue=None):
        if not self._validate_saved_instance(request, obj):
            return self._redirect_to_change(obj)
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if not self._validate_saved_instance(request, obj):
            return self._redirect_to_change(obj)
        return super().response_change(request, obj)

    def _validate_saved_instance(self, request, obj) -> bool:
        obj.refresh_from_db()
        try:
            obj.full_clean()
        except ValidationError as exc:
            self.message_user(
                request,
                _format_validation_error(exc),
                level=messages.ERROR,
            )
            self._revert_invalid_publish(obj)
            return False
        return True

    def _revert_invalid_publish(self, obj) -> None:
        if isinstance(obj, Survey) and obj.is_published:
            Survey.objects.filter(pk=obj.pk).update(is_published=False)

    def _redirect_to_change(self, obj) -> HttpResponseRedirect:
        url = reverse(
            f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change",
            args=[obj.pk],
        )
        return HttpResponseRedirect(url)


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 1


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    fields = ("order", "text", "type", "is_required")


@admin.register(Survey)
class SurveyAdmin(ValidateAfterSaveMixin, admin.ModelAdmin):
    list_display = ("title", "slug", "is_published", "created_at", "preview", "results")
    list_filter = ("is_published",)
    prepopulated_fields = {"slug": ("title",)}
    inlines = [QuestionInline]

    @admin.display(description="Preview")
    def preview(self, obj):
        url = reverse("surveys:preview", args=[obj.slug])
        return format_html('<a href="{}">Open</a>', url)

    @admin.display(description="Results")
    def results(self, obj):
        url = reverse("surveys:results", args=[obj.id])
        return format_html('<a href="{}">Open</a>', url)


@admin.register(Question)
class QuestionAdmin(ValidateAfterSaveMixin, admin.ModelAdmin):
    list_display = ("survey", "order", "short_text", "type", "is_required")
    list_filter = ("survey", "type", "is_required")
    inlines = [ChoiceInline]

    def get_inlines(self, request, obj=None):
        if obj and obj.type in {
            Question.Type.SINGLE_CHOICE,
            Question.Type.MULTIPLE_CHOICE,
        }:
            return [ChoiceInline]
        return []

    @admin.display(description="Question")
    def short_text(self, obj):
        return obj.text[:80]


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ("question", "order", "label")
    list_filter = ("question__survey",)


@admin.register(BranchRule)
class BranchRuleAdmin(admin.ModelAdmin):
    list_display = ("question", "choice", "next_question")
    list_filter = ("question__survey",)


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = (
        "question",
        "text_value",
        "number_value",
        "date_value",
        "choice",
        "multi_choices_display",
    )
    can_delete = False

    @admin.display(description="Choices (multiple)")
    def multi_choices_display(self, obj):
        if obj.pk is None:
            return ""
        return "; ".join(choice.label for choice in obj.choices.all())


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("survey", "uuid", "current_step", "started_at", "completed_at")
    list_filter = ("survey", "completed_at")
    readonly_fields = ("uuid", "started_at", "completed_at")
    inlines = [AnswerInline]

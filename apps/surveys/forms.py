from __future__ import annotations

from django import forms

from .constants import LONG_TEXT_MAX_LENGTH, SHORT_TEXT_MAX_LENGTH
from .lib import rating_value, trim_decimal
from .models import Answer, Question

BASE_INPUT_CLASS = (
    "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-slate-950 "
    "shadow-sm outline-none transition focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20 "
    "dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50"
)
CHOICE_CLASS = "space-y-2 text-sm text-slate-800 dark:text-slate-100"


def _error_list_id(auto_id: str) -> str:
    return f"{auto_id}-errors"


def _apply_accessibility_attrs(form: forms.Form) -> None:
    """Wire invalid fields to their error region for screen readers."""
    if not form.is_bound:
        return
    field = form["value"]
    if not field.errors:
        return
    error_id = _error_list_id(field.auto_id)
    widget = form.fields["value"].widget
    widget.attrs.setdefault("aria-invalid", "true")
    widget.attrs.setdefault("aria-describedby", error_id)


class QuestionForm(forms.Form):
    def __init__(self, *args, question: Question, **kwargs):
        self.question = question
        super().__init__(*args, **kwargs)


def _initial_for(instance: Answer | None):
    if not instance:
        return None
    qtype = instance.question.type
    if qtype in {Question.Type.SHORT_TEXT, Question.Type.LONG_TEXT}:
        return instance.text_value
    if qtype == Question.Type.NUMBER:
        return instance.number_value
    if qtype == Question.Type.RATING and instance.number_value is not None:
        return _initial_rating_choice_id(instance)
    if qtype == Question.Type.DATE and instance.date_value:
        return instance.date_value.isoformat()
    if qtype in {Question.Type.SINGLE_CHOICE, Question.Type.LIKERT}:
        return instance.choice_id
    if qtype == Question.Type.MULTIPLE_CHOICE and instance.pk:
        return list(instance.choices.values_list("id", flat=True))
    return None


def form_for_question(
    question: Question, *, data=None, instance: Answer | None = None
) -> forms.Form:
    required = question.is_required
    initial = _initial_for(instance)
    choices = question.choices.all()

    if question.type == Question.Type.SHORT_TEXT:
        field = forms.CharField(
            required=required,
            initial=initial,
            max_length=SHORT_TEXT_MAX_LENGTH,
            widget=forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "autocomplete": "off"}),
        )
    elif question.type == Question.Type.LONG_TEXT:
        field = forms.CharField(
            required=required,
            initial=initial,
            max_length=LONG_TEXT_MAX_LENGTH,
            widget=forms.Textarea(attrs={"class": BASE_INPUT_CLASS, "rows": 5}),
        )
    elif question.type == Question.Type.NUMBER:
        field = forms.DecimalField(
            required=required,
            initial=initial,
            max_digits=12,
            decimal_places=2,
            widget=forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "step": "0.01"}),
        )
    elif question.type == Question.Type.DATE:
        field = forms.DateField(
            required=required,
            initial=initial,
            widget=forms.DateInput(attrs={"class": BASE_INPUT_CLASS, "type": "date"}),
        )
    elif question.type in {Question.Type.SINGLE_CHOICE, Question.Type.LIKERT}:
        field = forms.ModelChoiceField(
            required=required,
            initial=initial,
            queryset=choices,
            empty_label=None,
            widget=forms.RadioSelect(attrs={"class": CHOICE_CLASS}),
        )
    elif question.type == Question.Type.MULTIPLE_CHOICE:
        field = forms.ModelMultipleChoiceField(
            required=required,
            initial=initial,
            queryset=choices,
            widget=forms.CheckboxSelectMultiple(attrs={"class": CHOICE_CLASS}),
        )
    elif question.type == Question.Type.RATING:
        field = forms.ModelChoiceField(
            required=required,
            initial=initial,
            queryset=choices,
            empty_label=None,
            widget=forms.RadioSelect(attrs={"class": CHOICE_CLASS}),
        )
    else:
        raise ValueError(f"Unsupported question type: {question.type}")

    form = type("DynamicQuestionForm", (QuestionForm,), {"value": field})(
        data=data,
        question=question,
    )
    form.fields["value"].label = question.text
    _apply_accessibility_attrs(form)
    return form


def _initial_rating_choice_id(instance: Answer) -> int | None:
    """Match stored rating number_value back to a Choice (label or order fallback)."""
    if instance.number_value is None:
        return None
    stored = instance.number_value.normalize()
    for choice in instance.question.choices.all():
        choice_rating = rating_value(choice)
        if choice_rating is not None and choice_rating.normalize() == stored:
            return choice.id
    label = trim_decimal(instance.number_value)
    choice = instance.question.choices.filter(label=label).first()
    return choice.id if choice else None

from __future__ import annotations

from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .managers import AnswerQuerySet, ResponseQuerySet, SurveyQuerySet


class Survey(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    intro = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SurveyQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        errors = {}
        if self.is_published and self.pk:
            questions = self.questions.prefetch_related("choices")
            if not questions.exists():
                errors["is_published"] = "Published surveys must have at least one question."
            for question in questions:
                if question.accepts_choices and not question.choices.exists():
                    errors["is_published"] = (
                        f'Question "{question.text[:50]}" ({question.get_type_display()}) '
                        "requires at least one choice before publishing."
                    )
                    break
        if errors:
            raise ValidationError(errors)


class Question(models.Model):
    class Type(models.TextChoices):
        SHORT_TEXT = "short_text", "Short text"
        LONG_TEXT = "long_text", "Long text"
        SINGLE_CHOICE = "single_choice", "Single choice"
        MULTIPLE_CHOICE = "multiple_choice", "Multiple choice"
        RATING = "rating", "Rating"
        LIKERT = "likert", "Likert"
        DATE = "date", "Date"
        NUMBER = "number", "Number"

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    order = models.PositiveIntegerField()
    type = models.CharField(max_length=32, choices=Type.choices)
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["survey", "order"], name="unique_question_order_per_survey"
            )
        ]

    def __str__(self) -> str:
        return f"{self.survey}: Q{self.order}"

    @property
    def accepts_choices(self) -> bool:
        return self.type in {
            self.Type.SINGLE_CHOICE,
            self.Type.MULTIPLE_CHOICE,
            self.Type.RATING,
            self.Type.LIKERT,
        }

    def clean(self) -> None:
        errors = {}
        if self.accepts_choices and self.pk and not self.choices.exists():
            errors["type"] = "This question type requires at least one choice."
        if errors:
            raise ValidationError(errors)


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    label = models.CharField(max_length=200)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "order"], name="unique_choice_order_per_question"
            )
        ]

    def __str__(self) -> str:
        return self.label


class BranchRule(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="branch_rules")
    choice = models.ForeignKey(Choice, on_delete=models.CASCADE, related_name="branch_rules")
    next_question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="incoming_branch_rules"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["question", "choice"], name="unique_branch_rule_choice")
        ]

    def __str__(self) -> str:
        return f"If {self.question} = {self.choice}, go to {self.next_question}"

    def clean(self) -> None:
        errors = {}
        if self.question_id and self.question.type != Question.Type.SINGLE_CHOICE:
            errors["question"] = "Branching is only supported for single-choice questions."
        if self.choice_id and self.question_id and self.choice.question_id != self.question_id:
            errors["choice"] = "The branch choice must belong to the branch question."
        if (
            self.next_question_id
            and self.question_id
            and self.next_question.survey_id != self.question.survey_id
        ):
            errors["next_question"] = "The next question must belong to the same survey."
        if (
            self.next_question_id
            and self.question_id
            and self.next_question_id == self.question_id
        ):
            errors["next_question"] = "The next question cannot be the same as the branch question."
        if self.question_id and self.next_question_id:
            from .pathing import branch_rule_creates_cycle

            if branch_rule_creates_cycle(self):
                errors["next_question"] = "Branch rules cannot form a cycle between questions."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Response(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid4, editable=False)
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="responses")
    current_step = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = ResponseQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.survey} response {self.uuid}"

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    @property
    def completion_seconds(self) -> int | None:
        if not self.completed_at:
            return None
        return int((self.completed_at - self.started_at).total_seconds())

    def mark_complete(self) -> None:
        self.completed_at = timezone.now()


class Answer(models.Model):
    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    text_value = models.TextField(blank=True)
    number_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    date_value = models.DateField(null=True, blank=True)
    choice = models.ForeignKey(
        Choice, null=True, blank=True, on_delete=models.SET_NULL, related_name="single_answers"
    )
    choices = models.ManyToManyField(Choice, blank=True, related_name="multi_answers")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AnswerQuerySet.as_manager()

    class Meta:
        ordering = ["question__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["response", "question"], name="unique_answer_per_response"
            )
        ]

    def __str__(self) -> str:
        return f"{self.response_id}: {self.question_id}"

    def clean(self) -> None:
        errors = {}
        qtype = self.question.type
        has_text = bool(self.text_value)
        has_number = self.number_value is not None
        has_date = self.date_value is not None
        has_choice = self.choice_id is not None

        if qtype in {Question.Type.SHORT_TEXT, Question.Type.LONG_TEXT}:
            if has_number or has_date or has_choice:
                errors["text_value"] = (
                    "Text answers cannot also store number, date, or choice data."
                )
        elif qtype == Question.Type.NUMBER:
            if has_text or has_date or has_choice:
                errors["number_value"] = (
                    "Number answers cannot also store text, date, or choice data."
                )
        elif qtype == Question.Type.DATE:
            if has_text or has_number or has_choice:
                errors["date_value"] = (
                    "Date answers cannot also store text, number, or choice data."
                )
        elif qtype == Question.Type.RATING:
            if has_text or has_date or has_choice:
                errors["number_value"] = "Rating answers are stored as a number only."
        elif qtype in {Question.Type.SINGLE_CHOICE, Question.Type.LIKERT}:
            if has_text or has_number or has_date:
                errors["choice"] = "Choice answers cannot also store text, number, or date data."
            if self.choice_id and self.choice.question_id != self.question_id:
                errors["choice"] = "Selected choice must belong to the answered question."
        elif qtype == Question.Type.MULTIPLE_CHOICE:
            if has_text or has_number or has_date or has_choice:
                errors["choices"] = (
                    "Multiple-choice answers are stored only in the choices relation."
                )

        if (
            self.response_id
            and self.question_id
            and self.response.survey_id != self.question.survey_id
        ):
            errors["question"] = "The answer question must belong to the response survey."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

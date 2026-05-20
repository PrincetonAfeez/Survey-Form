"""Signals for surveys app"""

from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Choice, Question

RATING_LABELS = ["1", "2", "3", "4", "5"]
LIKERT_LABELS = [
    "Strongly disagree",
    "Disagree",
    "Neutral",
    "Agree",
    "Strongly agree",
]


@receiver(pre_save, sender=Question)
def remember_question_type(sender, instance: Question, **kwargs) -> None:
    if instance.pk:
        instance._previous_type = (
            Question.objects.filter(pk=instance.pk).values_list("type", flat=True).first()
        )
    else:
        instance._previous_type = None


@receiver(post_save, sender=Question)
def seed_scale_choices(sender, instance: Question, created: bool, **kwargs) -> None:
    # Run on create and update: type changes into RATING/LIKERT need seeding; changes
    # away from choice-using types need cleanup (see accepts_choices branch below).
    if instance.type == Question.Type.RATING:
        labels = RATING_LABELS
    elif instance.type == Question.Type.LIKERT:
        labels = LIKERT_LABELS
    elif not instance.accepts_choices:
        if instance.answers_reference_choices():
            raise ValidationError(
                {
                    "type": "Cannot change type: answers reference existing choices.",
                }
            )
        instance.choices.all().delete()
        return
    else:
        return

    previous_type = getattr(instance, "_previous_type", None)
    converting_to_scale = previous_type not in (
        None,
        instance.type,
        *Question._AUTO_SEEDED_TYPES,
    )
    existing = list(instance.choices.order_by("order").values_list("label", flat=True))
    if existing == labels:
        return
    if existing and not converting_to_scale:
        return

    instance.choices.all().delete()
    Choice.objects.bulk_create(
        [
            Choice(question=instance, label=label, order=index)
            for index, label in enumerate(labels, 1)
        ]
    )

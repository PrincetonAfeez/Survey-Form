from apps.surveys.models import BranchRule, Choice, Question, Survey
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed a branching demo survey."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-admin",
            action="store_true",
            help="Create a dev staff user admin/admin12345 if one does not exist.",
        )

    def handle(self, *args, **options):
        survey, _ = Survey.objects.update_or_create(
            slug="remote-work-readiness",
            defaults={
                "title": "Remote Work Readiness",
                "intro": (
                    "A compact branching survey for evaluating workspace, tooling, "
                    "and collaboration readiness."
                ),
                "is_published": True,
            },
        )
        survey.questions.all().delete()

        q1 = Question.objects.create(
            survey=survey,
            order=1,
            text="Which work style best fits you right now?",
            type=Question.Type.SINGLE_CHOICE,
        )
        remote = Choice.objects.create(question=q1, order=1, label="Fully remote")
        Choice.objects.create(question=q1, order=2, label="Hybrid")
        Choice.objects.create(question=q1, order=3, label="Mostly office")

        q2 = Question.objects.create(
            survey=survey,
            order=2,
            text="How many minutes is your typical commute?",
            type=Question.Type.NUMBER,
            is_required=False,
        )
        q3 = Question.objects.create(
            survey=survey,
            order=3,
            text="How would you rate your home workspace?",
            type=Question.Type.RATING,
        )
        Question.objects.create(
            survey=survey,
            order=4,
            text="I can collaborate effectively without being in the same room.",
            type=Question.Type.LIKERT,
        )
        q5 = Question.objects.create(
            survey=survey,
            order=5,
            text="Which tools do you use every week?",
            type=Question.Type.MULTIPLE_CHOICE,
            is_required=False,
        )
        for order, label in enumerate(["Slack", "Teams", "Zoom", "Notion", "Google Docs"], 1):
            Choice.objects.create(question=q5, order=order, label=label)
        Question.objects.create(
            survey=survey,
            order=6,
            text="What would make your work setup meaningfully better?",
            type=Question.Type.LONG_TEXT,
            is_required=False,
        )

        BranchRule.objects.create(question=q1, choice=remote, next_question=q3)

        self.stdout.write(self.style.SUCCESS(f"Seeded survey: /s/{survey.slug}/"))
        self.stdout.write(f"Branch demo: choosing '{remote.label}' skips question {q2.order}.")

        if options["with_admin"]:
            User = get_user_model()
            if not User.objects.filter(username="admin").exists():
                User.objects.create_superuser(
                    username="admin", email="admin@example.com", password="admin12345"
                )
                self.stdout.write(self.style.SUCCESS("Created dev admin: admin / admin12345"))
            else:
                self.stdout.write("Dev admin already exists.")

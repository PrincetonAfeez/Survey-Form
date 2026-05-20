from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.surveys.models import Response


class Command(BaseCommand):
    help = "Delete incomplete survey responses older than N days (default 30)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Remove drafts started more than this many days ago (default 30).",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["days"])
        queryset = Response.objects.filter(completed_at__isnull=True, started_at__lt=cutoff)
        count, _ = queryset.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} draft response row(s)."))

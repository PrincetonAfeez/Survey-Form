"""Export a survey as JSON matching Schema/django-survey-definition.schema.json"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.surveys.models import Survey
from apps.surveys.schema_contract import (
    SURVEY_DEFINITION_SCHEMA_PATH,
    export_survey_definition,
    validate_json,
)


class Command(BaseCommand):
    help = "Export a survey as JSON matching Schema/django-survey-definition.schema.json"

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Survey slug to export")
        parser.add_argument(
            "--validate",
            action="store_true",
            help="Validate export against the JSON Schema (requires jsonschema)",
        )

    def handle(self, *args, **options):
        survey = Survey.objects.filter(slug=options["slug"]).first()
        if survey is None:
            raise CommandError(f"No survey with slug {options['slug']!r}")

        payload = export_survey_definition(survey)
        if options["validate"]:
            errors = validate_json(payload, SURVEY_DEFINITION_SCHEMA_PATH)
            if errors:
                raise CommandError("Schema validation failed:\n" + "\n".join(errors))

        self.stdout.write(json.dumps(payload, indent=2))

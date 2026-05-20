# Schema folder

JSON Schema and sample validators for this project. **Authoritative runtime validation** is in `apps/surveys/validation.py` (see `docs/validation.md`).

## Django app (use these)

| File | Purpose |
|------|---------|
| `django-survey-definition.schema.json` | Shape of `export_survey_definition()` — survey title, slug, questions, choices, branch rules |
| `django-wizard-answer.schema.json` | Documented shape of one wizard step (`export_wizard_answer()`) |

Export from the shell:

```powershell
.\.venv\Scripts\python manage.py export_survey_schema remote-work-readiness
```

Python API: `apps/surveys/schema_contract.py` (`export_survey_definition`, `validate_json` when `jsonschema` is installed).

### Question type mapping

| Django `Question.Type` | Schema `type` string |
|------------------------|----------------------|
| `short_text` | `short_text` |
| `long_text` | `long_text` |
| `single_choice` | `single_choice` |
| `multiple_choice` | `multiple_choice` |
| `rating` | `rating` |
| `likert` | `likert` |
| `date` | `date` |
| `number` | `number` |

## Legacy generic demos (not wired to Django)

These predate the Django app and describe a different HTML form shape (`text`, `email`, `radio`, etc.):

- `surveyFormSchema.json`
- `surveyResponseSchema.json`
- `validationSchema.js`
- `exampleResponse.json`

Keep them as reference for a standalone front-end; do not expect them to match `form_for_question()` or the ORM.

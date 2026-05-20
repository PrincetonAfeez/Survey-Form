# Architecture Decision Record
## App — Survey Form
**Survey Platform Group | Document 1 of 5**
**Status: Accepted**

---

## Context

The Survey Platform group requires a Django survey application that demonstrates more than a single HTML form. The app supports public surveys, question-by-question completion, server-rendered HTMX navigation, branch rules, session-backed drafts, signed resume links, staff preview, staff-only results, CSV/JSON exports, admin authoring, and testable domain boundaries.

The project is intentionally built as a survey platform rather than a hardcoded survey page. A survey can contain ordered questions of different types, choices, branch rules, responses, and typed answers. The system must render the right form for each question, save answers into the correct typed storage, calculate the next step, rebuild the response path, and summarize completed responses for staff users.

The decision was to build a Django 5 monolith with a repository/service-style boundary inside `apps.surveys`, using server-rendered templates and HTMX for incremental wizard behavior.

---

## Decisions

### Decision 1 — Django monolith over static HTML or frontend SPA

**Chosen:** Django 5, Django templates, ORM models, sessions, admin, and HTMX-enhanced server rendering.

**Rejected:** Static HTML, React/Next.js, or a separate API/frontend split.

**Reason:** The core learning goal is server-side form modeling, validation, branching, data storage, results aggregation, and admin authoring. Django directly supports those requirements. HTMX gives smooth step transitions without moving state management into JavaScript.

---

### Decision 2 — Data-driven survey model

**Chosen:** Model surveys with `Survey`, `Question`, `Choice`, `BranchRule`, `Response`, and `Answer`.

**Rejected:** Hardcoding the demo survey in views/templates.

**Reason:** Survey content should be authorable and testable as data. A normalized model supports multiple question types, ordering, publishing rules, branching rules, staff previews, exports, and results dashboards.

---

### Decision 3 — Typed answer columns instead of one JSON blob

**Chosen:** `Answer` stores values in typed fields: `text_value`, `number_value`, `date_value`, `choice`, and `choices`.

**Rejected:** A single JSON field for answer payloads.

**Reason:** Typed columns make validation, filtering, aggregation, CSV/JSON export, and admin display predictable. The model enforces that each question type stores data in the correct place.

---

### Decision 4 — Repository boundary for ORM access

**Chosen:** Use `SurveyRepository` and `ResponseRepository` for common query and persistence operations.

**Rejected:** Direct ORM queries scattered across runner, views, aggregators, and templates.

**Reason:** The survey flow is easier to reason about when database operations have names. Repositories centralize published survey lookup, staff lookup, question lookup, response start, answer save, answer search, and off-path pruning.

---

### Decision 5 — `SurveyRunner` for wizard orchestration

**Chosen:** A `SurveyRunner` owns current question lookup, form creation, submit handling, progress calculation, completion, and next-step decisions.

**Rejected:** Putting wizard progression entirely in views.

**Reason:** Views should handle HTTP and rendering. The runner holds the use-case logic: bind a dynamic form, validate it, save the answer if recording, compute the next question, move the response, or mark completion.

---

### Decision 6 — Separate navigation and pathing modules

**Chosen:** Keep branch-aware `next_question()` in `navigation.py` and response path reconstruction / branch-cycle detection in `pathing.py`.

**Rejected:** Putting all branching logic inside `SurveyRunner` or models.

**Reason:** Branching is important enough to isolate. Separating navigation avoids import cycles and makes cycle detection, saved-answer path rebuilds, and back-stack logic testable.

---

### Decision 7 — Branching limited to single-choice answers

**Chosen:** `BranchRule` applies only to single-choice questions and maps one choice to one next question.

**Rejected:** Branching on multiple-choice combinations, text values, numeric thresholds, or arbitrary expressions.

**Reason:** Single-choice branching is useful and understandable without creating a workflow rules engine. More complex branching would require a larger rule language and additional safety checks.

---

### Decision 8 — Session-backed response identity with signed resume links

**Chosen:** Active responses are stored in session by survey ID. A signed resume token can restore the response later.

**Rejected:** Public editable response IDs, accounts, or login-required survey taking.

**Reason:** Public surveys should be easy to take without accounts. Session state handles normal progress, and signed tokens allow controlled resume links without trusting raw URL identifiers.

---

### Decision 9 — Staff-only preview and results

**Chosen:** Preview, dashboard, raw responses, CSV export, and JSON export are protected with `staff_member_required`.

**Rejected:** Public results or anonymous preview access.

**Reason:** Survey response data should not be public by default. Staff-only access fits Django admin-style authoring and keeps the public interface focused on survey taking.

---

### Decision 10 — Tailwind and HTMX from CDN for demo scope

**Chosen:** `templates/base.html` loads Tailwind CDN and HTMX from unpkg.

**Rejected:** A compiled CSS/build pipeline for this version.

**Reason:** The README explicitly treats CDN Tailwind as acceptable for local/demo use and not recommended for production. This keeps the project small but leaves a known production hardening task.

---

## Consequences

**Positive:**
- Survey structure is data-driven and reusable.
- Dynamic forms support multiple question types from one factory.
- Typed answers improve validation and aggregation.
- Branching, back navigation, and resume links are implemented as first-class behavior.
- Staff users can preview and inspect results without saving preview answers.
- CSV/JSON exports support operational review.
- Admin authoring has validation safeguards.
- Seed command creates a working branching demo.

**Negative / Trade-offs:**
- The app is more complex than a simple survey form.
- Branching is intentionally limited to single-choice questions.
- Session-based progress can be lost if session data is cleared.
- Tailwind/HTMX CDN usage is not ideal for production.
- Results access depends on Django staff/admin access.
- No account system, per-user survey ownership, or analytics dashboard beyond built-in results.

---

## Alternatives Not Explored

- Full workflow rule engine.
- Anonymous public results sharing.
- Account-based survey management.
- Drag-and-drop survey builder.
- Client-side survey runtime.
- Compiled frontend asset pipeline.
- External analytics or BI integration.

---

*Constitution reference: Article 1 (architectural thinking), Article 3.4 (larger project classification), Article 4 (engineering quality), Article 6 (behavior verification), and Article 7 (progressive complexity).*

---


# Technical Design Document
## App — Survey Form
**Survey Platform Group | Document 2 of 5**

---

## Overview

Survey Form is a Django 5 survey platform with a public survey wizard, branching logic, session-backed responses, signed resume links, staff preview, staff-only results, raw response browsing, and CSV/JSON exports.

**Project package:** `config`  
**Primary app:** `apps.surveys`  
**Local settings:** `config.settings.dev`  
**Production settings:** `config.settings.prod`  
**Primary UI:** Django templates + HTMX  
**Local database:** SQLite by default  
**Production database:** PostgreSQL-ready through `DATABASE_URL`

---

## Data Flow

### Public survey start

```text
GET /s/<slug>/
     │
     ▼
survey_intro()
     │
     ▼
SurveyRepository.get_by_slug()
     │
     ▼
show intro and existing incomplete response if session has one
```

```text
POST /s/<slug>/start/
     │
     ▼
start_survey()
     │
     ▼
ResponseRepository.start()
     │
     ▼
create Response(current_step=first question order)
     │
     ▼
store response.uuid in session
     │
     ▼
redirect to /s/<slug>/step/<first_order>/
```

---

### Step submission

```text
POST /s/<slug>/step/<order>/
     │
     ▼
step()
     │
     ▼
SurveyRunner.submit()
     │
     ├── question_for_step()
     ├── form_for_question()
     ├── form.is_valid()
     ├── ResponseRepository.save_answer()
     ├── navigation.next_question()
     ├── move_to_step() or complete()
     └── prune off-route answers on completion
     │
     ▼
HTMX partial swap or normal redirect
```

---

### Branch/back path

```text
Session path: [question orders visited]
     │
     ├── _record_forward() appends next step
     ├── _path_step_back() removes current step and returns previous
     ├── build_path_from_response() reconstructs path from saved answers
     └── prune_answers_off_path() deletes skipped answers at completion
```

---

### Staff results

```text
GET /admin-results/<survey_id>/
     │
     ▼
staff_member_required
     │
     ▼
SurveyRepository.get_for_results()
     │
     ▼
aggregate_survey() + response_metrics()
     │
     ▼
results_dashboard.html
```

---

## Module-Level Structure

```text
Survey-Form/
  manage.py
  config/
    settings/base.py
    settings/dev.py
    settings/prod.py
    urls.py
    wsgi.py
    asgi.py
  apps/surveys/
    admin.py
    aggregators.py
    display.py
    forms.py
    managers.py
    models.py
    navigation.py
    pathing.py
    repositories.py
    runners.py
    signals.py
    tokens.py
    urls.py
    views.py
    management/commands/seed_survey.py
    templatetags/survey_extras.py
    tests/
  templates/
    base.html
    surveys/
  static/
  docs/adr/
  Makefile
  requirements.txt
  pyproject.toml
```

---

## Module Dependency Graph

```text
config.urls
  ├── django admin
  └── apps.surveys.urls

apps.surveys.urls
  └── apps.surveys.views

views.py
  ├── aggregators.aggregate_survey / response_metrics
  ├── display.format_answer_value
  ├── pathing.build_path_from_response
  ├── repositories.SurveyRepository / ResponseRepository
  ├── runners.SurveyRunner
  └── tokens.issue_resume_token / verify_resume_token

runners.py
  ├── forms.form_for_question
  ├── navigation.next_question / choice_from_saved_response
  ├── pathing.build_path_from_response
  └── repositories

repositories.py
  ├── models
  └── transaction.atomic

pathing.py
  ├── BranchRule / Question
  ├── navigation
  └── repositories

forms.py
  ├── Django forms
  ├── display.trim_decimal
  ├── models.Answer / Question
  └── repositories.rating_value
```

---

## Core Data Structures

### `Survey`

Fields:
- `title`
- `slug`
- `intro`
- `is_published`
- timestamps

Rules:
- published surveys must have questions
- choice-based questions must have choices before publication

---

### `Question`

Question types:
- `short_text`
- `long_text`
- `single_choice`
- `multiple_choice`
- `rating`
- `likert`
- `date`
- `number`

Fields:
- `survey`
- `text`
- `order`
- `type`
- `is_required`

Constraint:
```text
unique question order per survey
```

---

### `Choice`

Fields:
- `question`
- `label`
- `order`

Constraint:
```text
unique choice order per question
```

---

### `BranchRule`

Fields:
- `question`
- `choice`
- `next_question`

Rules:
- source question must be single-choice
- branch choice must belong to the source question
- target question must belong to the same survey
- target question cannot be the same question
- branch graph cannot create a cycle

---

### `Response`

Fields:
- `uuid`
- `survey`
- `current_step`
- `started_at`
- `completed_at`

Computed:
- `is_complete`
- `completion_seconds`

---

### `Answer`

Fields:
- `response`
- `question`
- `text_value`
- `number_value`
- `date_value`
- `choice`
- `choices`
- timestamps

Constraint:
```text
unique answer per response/question
```

Type rules:
- text questions use `text_value`
- number and rating questions use `number_value`
- date questions use `date_value`
- single-choice and Likert use `choice`
- multiple-choice uses the `choices` relation

---

### `SubmitResult`

```python
@dataclass(frozen=True)
class SubmitResult:
    ok: bool
    form: forms.Form
    question: Question
    next_question: Question | None = None
    is_final: bool = False
```

Used by views to decide whether to re-render with errors, redirect, swap HTMX partials, or finish the survey.

---

## Function and Class Reference

### `form_for_question(question, data=None, instance=None)`

Builds a dynamic form for one question. It maps question type to a Django field and widget:
- text input
- textarea
- decimal number input
- date input
- radio buttons
- checkboxes

If an existing answer is supplied, it becomes the initial value.

---

### `SurveyRepository`

Important methods:
- `get_published()`
- `get_by_slug(slug)`
- `get_for_preview(survey_id, user)`
- `get_for_results(survey_id, user)`
- `questions_for_survey(survey)`
- `get_question_by_order(survey, order)`
- `get_next_question_by_order(survey, order)`
- `first_question_order(survey)`
- `get_branch_target(question, choice)`

---

### `ResponseRepository`

Important methods:
- `for_respondent(uuid)`
- `start(survey)`
- `answer_for(response, question)`
- `save_answer(response, question, payload)`
- `move_to_step(response, step)`
- `complete(response)`
- `filter_by_answer_query(queryset, query)`
- `prune_answers_off_path(response, path)`
- `list_for_survey(survey, complete_only=False)`

---

### `SurveyRunner`

Important methods:
- `current_question()`
- `question_for_step(step)`
- `step_number()`
- `total_questions()`
- `progress_percent(step)`
- `form_for(question, data=None)`
- `submit(payload, step=None)`
- `next_question(question, answered_choice)`
- `is_complete()`
- `has_next_step(question)`
- `is_final_step(question)`

The runner can operate in record mode or preview mode. Preview mode does not persist answers.

---

### `navigation.next_question()`

Returns a branch target when the current question is single-choice and the chosen answer has a branch rule. Otherwise returns the next question by order.

---

### `build_path_from_response()`

Reconstructs the branch-aware path from saved answers. It stops at:
- current step
- a detected cycle
- question-count safety limit
- no next question

---

### `branch_rule_creates_cycle()`

Builds the navigation graph using explicit branch rules and implicit next-by-order fallback edges. Returns true when adding a rule would create a cycle.

---

### `aggregate_survey()`

Returns per-question aggregate summaries for staff dashboard display.

Aggregation types:
- choice counts
- multiple-choice counts
- number/rating statistics
- recent text answers
- date counts by week

---

### `response_metrics()`

Returns:
- started count
- completed count
- completion rate
- median completion seconds

---

### `issue_resume_token(response)`

Signs response UUID and survey ID using Django signing.

---

### `verify_resume_token(token, max_age=30 days)`

Verifies and returns token payload or returns `None` on bad/expired signatures.

---

### `format_answer_value(answer)`

Converts typed answer storage to a display/export string.

---

## Error Handling Strategy

- Missing public survey slugs return 404.
- Starting a survey with no questions raises 404 via `ValueError`.
- Invalid question steps return 404 or redirect to the current safe step.
- Invalid resume tokens render an invalid-resume page with HTTP 400.
- Staff-only views require `staff_member_required`.
- Invalid branch rules raise `ValidationError`.
- Invalid typed answer storage raises `ValidationError`.
- HTMX invalid step submissions return status 422 and re-render the wizard partial.
- Export routes return staff-protected CSV/JSON only after survey lookup succeeds.

---

## External Dependencies

| Dependency | Purpose |
|---|---|
| Django | Web framework, ORM, forms, templates, admin, sessions |
| django-environ | `.env` and `DATABASE_URL` parsing |
| django-htmx | request HTMX detection |
| psycopg[binary] | PostgreSQL support |
| pytest | tests |
| pytest-django | Django test integration |
| hypothesis | property tests |
| ruff | linting |
| black | formatting |
| coverage | coverage enforcement |

Frontend:
- Tailwind CSS CDN
- HTMX from unpkg

---

## Concurrency Model

The app is synchronous Django. There are:
- no async views
- no background workers
- no task queue
- no websocket behavior

Concurrency is delegated to the WSGI/ASGI server and database. `save_answer()` uses `transaction.atomic` and `select_for_update()` around answer updates.

---

## Known Limitations

- Tailwind and HTMX are loaded from CDNs.
- No compiled frontend asset pipeline.
- No public API.
- No user account ownership model.
- No drag-and-drop survey builder.
- Branching only supports single-choice questions.
- Staff results are basic dashboard/export pages, not a full analytics product.
- Response resume depends on signed links and session behavior.
- Production deployment files beyond settings are minimal in the inspected files.
- README mentions a GitHub Actions workflow, but the workflow file was not available through the connector during this inspection.

---

## Design Patterns Used

- **Django MVT**
- **Repository pattern**
- **Runner/use-case object**
- **Dynamic form factory**
- **Typed answer model**
- **Branch-aware navigation**
- **Session path stack**
- **Signed token resume links**
- **Staff-only reporting**
- **Admin validation safeguards**
- **Seed command**

---

## Verification Summary

Verified evidence includes:
- model tests for string behavior, typed-answer validation, cross-survey protection, branch-rule validation, and auto-seeded rating/Likert choices
- README-documented 261 tests and 100% coverage target on `apps/surveys`
- coverage configuration with fail-under 100
- Makefile targets for tests, lint, formatting, migration, coverage, and seeding
- dynamic form behavior and accessibility attributes implemented in `forms.py`
- HTMX partial behavior implemented in views and templates

---

*Constitution reference: Article 4 (engineering quality), Article 6 (behavior verification), Article 7 (progressive complexity), and Article 8 (valid learner work).*

---


# Interface Design Specification
## App — Survey Form
**Survey Platform Group | Document 3 of 5**

---

## Public Web Interface

| Method | Path | View | Success Status | Description |
|---|---|---|---:|---|
| `GET` | `/` | `survey_list` | 200 | Public list of published surveys |
| `GET` | `/s/<slug>/` | `survey_intro` | 200 | Survey intro page |
| `POST` | `/s/<slug>/start/` | `start_survey` | 302 | Start or resume survey response |
| `GET` | `/s/<slug>/step/<order>/` | `step` | 200 | Render one question step |
| `POST` | `/s/<slug>/step/<order>/` | `step` | 200/204/302/422 | Submit one question |
| `GET` | `/s/<slug>/step/<order>/back/` | `step_back` | 302 | Move back in session path |
| `GET` | `/s/<slug>/resume/<token>/` | `resume` | 302/400 | Resume a response using signed token |
| `GET` | `/s/<slug>/done/` | `done` | 200/302 | Completion page |
| `GET` | `/s/<slug>/preview/` | `preview` | 302 | Staff-only preview start |
| `GET`/`POST` | `/s/<slug>/preview/step/<order>/` | `preview_step` | 200/302/422 | Staff-only preview step |
| `GET` | `/s/<slug>/preview/step/<order>/back/` | `preview_step_back` | 302 | Staff-only preview back |
| `GET` | `/admin-results/<id>/` | `results_dashboard` | 200 | Staff-only aggregate dashboard |
| `GET` | `/admin-results/<id>/raw/` | `results_raw` | 200 | Staff-only raw responses |
| `GET` | `/admin-results/<id>/export.csv` | `export_csv` | 200 | Staff-only CSV export |
| `GET` | `/admin-results/<id>/export.json` | `export_json` | 200 | Staff-only JSON export |
| any | `/admin/` | Django admin | varies | Survey authoring/admin |

---

## Invocation Syntax

### Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_survey --with-admin
.\.venv\Scripts\python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

---

### Make targets

```bash
make migrate
make run
make test
make lint
make format
make coverage
make seed
```

---

## Management Command Reference

### `seed_survey`

```bash
python manage.py seed_survey [--with-admin]
```

| Argument | Type | Required | Description |
|---|---|---|---|
| `--with-admin` | flag | No | Creates dev superuser `admin` / `admin12345` if missing |

Behavior:
- creates/updates survey `remote-work-readiness`
- deletes and recreates its questions
- creates single-choice, number, rating, Likert, multiple-choice, and long-text questions
- creates a branch rule where `Fully remote` skips the commute question
- optionally creates a dev admin user

---

## HTTP Input Contract

### Start survey

```text
POST /s/<slug>/start/
```

Optional body:
```text
force_new=1
```

If `force_new` is not set and an incomplete response exists in session, the user resumes that response.

---

### Submit step

```text
POST /s/<slug>/step/<order>/
```

Body key:
```text
value=<answer>
```

The expected value depends on the question type:
- string for text
- decimal for number
- date string for date
- choice ID for single-choice, Likert, and rating
- list of choice IDs for multiple-choice

---

### Raw response search

```text
GET /admin-results/<id>/raw/?q=<query>&page=<page>
```

Search matches:
- text answers
- single-choice labels
- multiple-choice labels
- ISO date input when parseable
- decimal number input when parseable

---

## Output Contract

### Step page

Includes:
- survey title
- current question
- progress bar
- dynamic question form
- required marker for required questions
- resume link when recording
- back URL when path allows back navigation

HTMX request:
- returns `surveys/partials/_wizard.html`

Normal request:
- returns `surveys/step.html`

Invalid HTMX submission:
```text
HTTP 422
```

---

### Successful HTMX submit

If another step exists:
- returns wizard partial for next question
- sets `HX-Push-Url`
- sets `HX-Trigger` with `draftSaved`

If final step:
- returns HTTP 204
- sets `HX-Redirect` to done/preview URL

---

### Resume link

A resume token encodes:
- response UUID
- survey ID

Invalid token:
```text
HTTP 400
```

Valid incomplete response:
```text
302 to current step
```

Valid complete response:
```text
302 to done page
```

---

### CSV export

Content type:
```text
text/csv
```

Filename:
```text
<survey-slug>-responses.csv
```

Columns:
- response UUID
- started at
- completed at
- one column per survey question

Only complete responses are exported.

---

### JSON export

Content type:
```text
application/json
```

Shape:
```json
[
  {
    "response": {
      "uuid": "...",
      "started_at": "...",
      "completed_at": "..."
    },
    "answers": [
      {
        "question": "...",
        "type": "...",
        "value": "..."
      }
    ]
  }
]
```

Only complete responses are exported.

---

## Exit Code Reference

The app defines no custom process exit codes.

| Command | Success | Failure |
|---|---:|---:|
| `python manage.py migrate` | 0 | non-zero on DB/migration error |
| `python manage.py seed_survey` | 0 | non-zero on command/model error |
| `python manage.py runserver` | 0 on clean exit | non-zero on startup error |
| `pytest` | 0 | non-zero on test failure |
| `coverage report --fail-under=100` | 0 | non-zero below threshold |
| `ruff check .` | 0 | non-zero on lint failure |
| `black .` | 0 | non-zero on formatting/runtime failure |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | operationally | `config.settings.dev` or `config.settings.prod` |
| `SECRET_KEY` | production | Django secret |
| `DEBUG` | no | Boolean debug flag |
| `ALLOWED_HOSTS` | production | Production host allowlist |
| `DATABASE_URL` | optional locally, production DB | SQLite default or PostgreSQL URL |
| `LOG_LEVEL` | no | Production logging level |

---

## Configuration Files

### `.env`

Optional local file read by `django-environ`.

---

### `requirements.txt`

Runtime and tooling dependencies:
- Django
- django-environ
- django-htmx
- psycopg
- pytest
- pytest-django
- hypothesis
- ruff
- black
- coverage

---

### `pyproject.toml`

Configures:
- project metadata
- Python `>=3.12`
- Black
- Ruff
- pytest
- coverage fail-under 100 on `apps/surveys`

---

### `Makefile`

Defines:
- `run`
- `migrate`
- `seed`
- `test`
- `lint`
- `format`
- `coverage`

---

## Side Effects

| Operation | Side Effect |
|---|---|
| Start survey | Creates `Response` and stores UUID in session |
| Submit answer | Creates/updates typed `Answer` |
| Branch submit | Updates `Response.current_step` based on branch/fallback |
| Complete survey | Sets `completed_at` |
| Completion | Prunes off-route answers |
| Back navigation | Updates session path and `current_step` |
| Resume link | Re-associates response UUID with current session |
| Preview | Uses session path but does not save answers |
| Seed command | Recreates demo survey questions and optional admin user |
| Admin publish/save | Validates survey/question rules |
| CSV/JSON export | Streams staff-only export responses |

---

## Usage Examples

### Seed and run

```powershell
python manage.py migrate
python manage.py seed_survey --with-admin
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/s/remote-work-readiness/
```

---

### Staff login

```text
/admin/
```

Seeded credentials when using `--with-admin`:

```text
admin / admin12345
```

---

### Staff preview

```text
/s/remote-work-readiness/preview/
```

---

### Staff results

```text
/admin-results/<survey_id>/
```

---

### Export responses

```text
/admin-results/<survey_id>/export.csv
/admin-results/<survey_id>/export.json
```

---

### Intentional failure — invalid resume token

```text
/s/remote-work-readiness/resume/not-a-valid-token/
```

Expected:
```text
HTTP 400
```

---

### Intentional failure — invalid branch rule

A branch rule whose source question is not single-choice or whose target creates a cycle raises `ValidationError`.

---

## Public Python Interfaces

Important internal interfaces:
- `form_for_question`
- `SurveyRepository`
- `ResponseRepository`
- `SurveyRunner`
- `SubmitResult`
- `next_question`
- `build_path_from_response`
- `branch_rule_creates_cycle`
- `aggregate_survey`
- `response_metrics`
- `issue_resume_token`
- `verify_resume_token`
- `format_answer_value`

---

*Constitution reference: Article 4 (input/output boundaries), Article 6 (verification), and Article 8 (understandable and verifiable work).*

---


# Runbook
## App — Survey Form
**Survey Platform Group | Document 4 of 5**

---

## Requirements

- Python 3.12+
- pip
- virtual environment support
- SQLite for local development
- PostgreSQL-ready environment for production
- Make optional, but useful
- Browser with JavaScript enabled for HTMX-enhanced wizard behavior

---

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_survey --with-admin
.\.venv\Scripts\python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

---

## Configuration

### Development

Default through `manage.py`:

```text
config.settings.dev
```

Behavior:
- `DEBUG = True`
- local hosts only
- console email backend
- SQLite default through `DATABASE_URL` fallback

---

### Production

Set:

```text
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=<strong-secret>
ALLOWED_HOSTS=<production-hosts>
DATABASE_URL=<postgres-url>
```

Production behavior:
- debug disabled
- explicit hosts required
- HTTPS redirect enabled
- secure session/CSRF cookies
- HSTS enabled
- proxy SSL header configured
- console logging configured

---

## Running the App

### Development server

```powershell
python manage.py runserver
```

Expected:
- `/` shows published surveys
- seeded demo appears after `seed_survey`
- `/s/remote-work-readiness/` opens intro page
- survey can be completed through the wizard

---

## Running Tests

### Default tests

```powershell
pytest
```

---

### Coverage

```powershell
coverage run -m pytest
coverage report --fail-under=100 --include="apps/surveys/*" --omit="*/migrations/*,*/tests/*"
```

---

### Lint

```powershell
ruff check .
```

---

### Format

```powershell
black .
ruff check . --fix
```

---

## Standard Operating Procedures

### Start from clean local database

```powershell
Remove-Item db.sqlite3
python manage.py migrate
python manage.py seed_survey --with-admin
python manage.py runserver
```

---

### Create demo survey

```powershell
python manage.py seed_survey --with-admin
```

Expected:
```text
Seeded survey: /s/remote-work-readiness/
Branch demo: choosing 'Fully remote' skips question 2.
```

---

### Take survey as public user

1. Open `/`.
2. Select `Remote Work Readiness`.
3. Start survey.
4. Answer each step.
5. Use Back when available.
6. Complete the survey.
7. Confirm done page.

---

### Resume incomplete survey

1. Start a survey.
2. Copy the displayed resume link.
3. Open it in the same or another browser session.
4. Confirm it redirects to current step or done page.

---

### Preview as staff

1. Seed with admin.
2. Login at `/admin/`.
3. Open `/s/remote-work-readiness/preview/`.
4. Answer preview steps.
5. Confirm preview does not save answers.

---

### View results

1. Login as staff.
2. Open `/admin-results/<survey_id>/`.
3. Review metrics and aggregates.
4. Open raw responses.
5. Export CSV or JSON.

---

### Add survey through admin

1. Create `Survey`.
2. Add ordered `Question` rows.
3. Add choices for choice-based questions.
4. Add `BranchRule` rows only for single-choice questions.
5. Publish only after validation passes.
6. Use Preview before making it public.

---

## Health Checks

### Public list

```text
GET /
```

Healthy:
- HTTP 200
- published surveys visible

---

### Seeded survey intro

```text
GET /s/remote-work-readiness/
```

Healthy:
- HTTP 200
- intro content visible

---

### Wizard step

```text
GET /s/remote-work-readiness/step/1/
```

Healthy when response exists:
- HTTP 200
- question rendered
- progress bar visible

Without response:
- redirects to intro

---

### Staff results

```text
GET /admin-results/<survey_id>/
```

Healthy:
- staff user gets HTTP 200
- anonymous user redirects to admin login

---

### Export

```text
GET /admin-results/<survey_id>/export.csv
GET /admin-results/<survey_id>/export.json
```

Healthy:
- staff user receives file/JSON response
- anonymous user is blocked by staff login requirement

---

## Expected Output Samples

### Seed command

```text
Seeded survey: /s/remote-work-readiness/
Branch demo: choosing 'Fully remote' skips question 2.
Created dev admin: admin / admin12345
```

---

### Coverage

```text
coverage report --fail-under=100 --include="apps/surveys/*" --omit="*/migrations/*,*/tests/*"
```

Expected:
- exits 0 only at or above 100% threshold

---

### Invalid resume link

```text
HTTP 400
```

Template:
```text
resume_invalid.html
```

---

## Known Failure Modes

### No surveys appear on `/`

**Trigger:** No published surveys or seed command not run.

**Fix:**
```powershell
python manage.py seed_survey --with-admin
```

---

### Published survey validation fails

**Trigger:** Survey has no questions, or a choice-based question has no choices.

**Fix:**
- add questions
- add required choices
- retry publish

---

### Branch rule fails validation

**Common causes:**
- source question is not single-choice
- choice belongs to another question
- target question belongs to another survey
- target is the same question
- rule creates a cycle

**Fix:**
- correct source/choice/target
- keep branching acyclic

---

### Resume link invalid

**Trigger:** Token is malformed, expired, signed with a different secret, or points to a missing/wrong survey response.

**Fix:**
- use a fresh resume link from the active step page

---

### Step redirects unexpectedly

**Trigger:** Requested step is not on current session path or response current step differs.

**Fix:**
- use the rendered Next/Back controls instead of manually editing URLs

---

### Staff results inaccessible

**Trigger:** User is not authenticated staff.

**Fix:**
```powershell
python manage.py seed_survey --with-admin
```

Then login:
```text
admin / admin12345
```

---

### Production startup fails

**Trigger:** Missing `ALLOWED_HOSTS` or invalid production environment.

**Fix:**
Set:
```text
ALLOWED_HOSTS=<hostnames>
SECRET_KEY=<secret>
DATABASE_URL=<postgres-url>
```

---

### CDN assets unavailable

**Trigger:** Tailwind CDN or unpkg HTMX is blocked/unavailable.

**Effect:**
- page may still render
- styling/interactivity may degrade

**Fix:**
- replace with compiled, self-hosted assets for production

---

## Troubleshooting Decision Tree

```text
App does not start
  ├── Dependencies missing?
  │     └── pip install -r requirements.txt
  ├── Database unmigrated?
  │     └── python manage.py migrate
  ├── Production env missing?
  │     └── set SECRET_KEY, ALLOWED_HOSTS, DATABASE_URL
  └── Wrong settings?
        └── use config.settings.dev locally

Survey not available
  ├── No seed data?
  │     └── python manage.py seed_survey --with-admin
  ├── Survey unpublished?
  │     └── publish in admin after validation
  └── No questions/choices?
        └── add valid questions and choices

Wizard behavior wrong
  ├── Session lost?
  │     └── restart survey or use resume link
  ├── Step not in path?
  │     └── use normal Next/Back navigation
  ├── Branch target wrong?
  │     └── inspect BranchRule
  └── Cycle rejected?
        └── revise branch graph

Results/export blocked
  ├── Not staff?
  │     └── login through admin
  ├── No completed responses?
  │     └── complete a survey
  └── Query too narrow?
        └── clear raw response search
```

---

## Dependency Failure Handling

### Python dependencies

```powershell
python -m pip install -r requirements.txt
```

---

### PostgreSQL

Check:
- `DATABASE_URL`
- migrations
- database availability
- psycopg installation

---

### Frontend CDN

Long-term production fix:
- vendor or compile HTMX locally
- compile Tailwind CSS
- serve through Django static files/WhiteNoise/CDN

---

## Recovery Procedures

### Recover from bad local DB

```powershell
Remove-Item db.sqlite3
python manage.py migrate
python manage.py seed_survey --with-admin
```

---

### Recover from bad branch rules

1. Login to admin.
2. Remove invalid `BranchRule`.
3. Re-add one rule at a time.
4. Save and allow model validation to catch cycles.

---

### Recover from broken survey authoring

1. Unpublish survey.
2. Fix question order and choices.
3. Preview as staff.
4. Publish after validation passes.

---

### Recover from lost session

Use the signed resume link if available. If no resume link exists, restart the survey.

---

## Logging Reference

Production defines console logging with a verbose formatter and configurable root `LOG_LEVEL`.

Important operational events are mainly visible through:
- Django request/security logs
- command output
- admin validation messages
- test/coverage output

There is no custom application log file.

---

## Maintenance Notes

- Keep branching single-choice unless a larger rules engine is intentionally designed.
- Keep `Answer.clean()` aligned with new question types.
- Add tests before adding question types or export formats.
- Keep admin validation strong because survey authors can create invalid graphs.
- Replace CDN Tailwind/HTMX before serious production deployment.
- Keep signed resume-token max age intentional.
- Keep coverage threshold realistic and update tests with behavior changes.
- Verify README-mentioned CI workflow exists before relying on automated enforcement.

---

*Constitution reference: Article 6 (behavior verification), Article 5 (constraints and trade-offs), and Article 8 (verifiable learner work).*

---


# Lessons Learned
## App — Survey Form
**Survey Platform Group | Document 5 of 5**

---

## Why This Design Was Chosen

This design was chosen because a survey application is mostly about state and flow. The interesting problem is not rendering one form. The interesting problem is deciding which question appears next, saving the right answer type, allowing back navigation, resuming incomplete responses, preventing invalid branch graphs, and summarizing completed answers.

Django was the right framework because it provides the model, form, session, admin, template, and permission tools needed for a survey platform. HTMX was enough for the step-by-step experience. A separate JavaScript application would have added complexity without improving the core learning goals.

The repository and runner boundaries were the most important architectural choices. They keep database access, survey progression, and HTTP rendering from collapsing into one large view file. That makes the project easier to test and explain.

---

## What Was Intentionally Omitted

**Account-based survey taking:** Public respondents do not need accounts. Sessions and signed resume tokens are enough for this version.

**Public results:** Results are staff-only.

**Complex branch expressions:** Branching is limited to single-choice answers.

**Drag-and-drop builder:** Survey authoring uses Django admin, not a custom builder UI.

**Compiled frontend build:** Tailwind and HTMX are loaded from CDNs for demo scope.

**API-first design:** The app is server-rendered. No public JSON API is provided except staff JSON export.

**External analytics:** Aggregation is handled inside the app.

---

## Biggest Weakness

The biggest weakness is production frontend readiness. Tailwind CDN and unpkg-hosted HTMX are acceptable for a demo, but they are not ideal for production. A production version should compile Tailwind, self-host HTMX, add a stricter Content Security Policy, and remove third-party runtime dependencies.

The second weakness is that branching is intentionally simple. Single-choice branching keeps the mental model clean, but real survey tools often need more complex logic. Expanding that feature would require a carefully designed rule model, validation, preview tools, and tests.

The third weakness is that there is no custom survey builder. Django admin is powerful enough for this project, but it is not a friendly survey-authoring UI for non-technical staff.

---

## Scaling Considerations

**If surveys grow larger:**
- add pagination/index review for raw responses
- consider response export streaming for very large exports
- add database indexes for common answer searches
- review session path size

**If branching grows:**
- introduce a formal branch condition model
- build visual branch validation
- add branch graph preview
- expand cycle detection tests

**If many staff users author surveys:**
- add a custom builder UI
- add author permissions
- add draft/publish workflows
- add change history

**If production traffic grows:**
- compile and self-host frontend assets
- add stricter CSP
- add PostgreSQL connection tuning
- add deployment health checks
- add backups and export retention policy

---

## What the Next Refactor Would Be

1. **Replace CDN frontend assets** — compile Tailwind and self-host HTMX.

2. **Add production deployment files** — add explicit Gunicorn/WhiteNoise deployment instructions or Procfile-style config.

3. **Add a custom authoring UI** — make survey creation easier than Django admin.

4. **Add branch graph visualization** — help staff understand and debug survey flow.

5. **Add more export controls** — date range, complete-only toggle, and selected columns.

---

## What This Project Taught

- **Survey logic is graph logic.** Even a simple branch rule creates navigation paths, cycle risks, off-route answers, and back-stack complexity.

- **Typed storage pays off.** Typed answer columns make validation and results easier than generic JSON for this project.

- **Sessions are useful but fragile.** They make public survey taking easy, but resume links are needed for recovery.

- **Admin can be a real authoring surface.** With validation and preview links, Django admin becomes more than a database editor.

- **HTMX fits wizard flows.** It gives smooth step transitions without moving the survey engine into JavaScript.

- **Exports require display discipline.** One formatter keeps CSV, JSON, raw tables, and templates consistent.

- **Tests define survey behavior.** Branch rules, typed answers, seeded choices, navigation, and aggregation all need tests because small mistakes can corrupt response data.

---

*Constitution v2.0 checklist: This document satisfies Article 5 (trade-off documentation), Article 6 (verification), and Article 7 (progressive complexity) for Survey Form.*

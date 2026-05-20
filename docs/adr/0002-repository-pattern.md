# 0002 - Repository Pattern In A Django App

## Status

Accepted

## Context

Django models already expose a rich ORM API, but views can become tightly coupled to query details.

## Decision

Route survey and response data access through `SurveyRepository` and `ResponseRepository`. Managers expose reusable QuerySets; repositories translate them into domain language.

## Consequences

The app has a little more ceremony than a small Django CRUD project, but the runner and views stay focused on workflow rather than query construction.

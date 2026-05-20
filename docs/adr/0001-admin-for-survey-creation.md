# 0001 - Django Admin For Survey Creation

## Status

Accepted

## Context

Survey authors need CRUD for surveys, questions, choices, and branch rules. Building a bespoke authoring interface would consume most of the project budget while adding little to the respondent flow.

## Decision

Use Django admin for survey creation and maintenance. Build custom UI only for respondent flow and results.

## Consequences

The project demonstrates architecture where it matters most: runner orchestration, repositories, branching, signed resume tokens, and aggregation. Authoring UX remains utilitarian but reliable.

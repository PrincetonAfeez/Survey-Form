# 0004 - Typed-Column Answer Polymorphism

## Status

Accepted

## Context

Answers can be text, number, date, single choice, or multiple choice. JSON would be flexible, but harder to query and validate.

## Decision

Store answer values in typed columns on `Answer`: `text_value`, `number_value`, `date_value`, `choice`, and `choices`.

## Consequences

Aggregates and exports can use normal SQL-friendly fields. `Answer.clean()` enforces that an answer only populates the fields appropriate for its question type.

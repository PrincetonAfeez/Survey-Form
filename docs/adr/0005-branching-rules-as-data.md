# 0005 - Branching Via BranchRule Table

## Status

Accepted

## Context

Branching can be encoded in code or represented as editable survey data.

## Decision

Use explicit `BranchRule(question, choice, next_question)` rows. Absence of a rule falls back to the next ordered question.

## Consequences

The runner stays generic and admin users can manage branch paths. Version 1 supports single-choice branching only; multi-choice branching would need set logic and conflict resolution.

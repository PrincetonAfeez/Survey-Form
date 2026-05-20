# 0007 - UUID Respondent Identity

## Status

Accepted

## Context

Respondents need stable identity across sessions without requiring accounts.

## Decision

Give each `Response` a UUID. Store it in the session during the current visit and in signed resume tokens for later access.

## Consequences

Links do not expose sequential ids, session loss is recoverable, and the data model remains account-free for respondents.

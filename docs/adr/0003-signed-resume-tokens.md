# 0003 - Signed Tokens Via django.core.signing

## Status

Accepted

## Context

Respondents need a resume link that does not expose sequential database ids and can expire.

## Decision

Use `django.core.signing` with a dedicated salt and a 30-day max age. The token stores the response UUID and survey id.

## Consequences

No JWT dependency is required, tokens are tamper-evident, and verification remains integrated with Django's configured secret key.
